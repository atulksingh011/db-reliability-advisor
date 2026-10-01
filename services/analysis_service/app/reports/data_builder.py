"""Builds presentation data from trusted Contract B inputs only."""

import re
from dataclasses import dataclass

from ..contracts.models import (
    AnalysisPackage,
    ChartPoint,
    Evidence,
    ReportChart,
    ReportFact,
    VerificationQuery,
)


@dataclass(frozen=True)
class TrustedReportSection:
    facts: list[ReportFact]
    charts: list[ReportChart]
    verification: list[VerificationQuery]
    chart_evidence_ids: dict[str, list[str]]


@dataclass(frozen=True)
class TrustedReportData:
    sections: dict[str, TrustedReportSection]


class TrustedReportDataBuilder:
    """Translate Contract B into report-safe values without calling AI or storage."""

    def build(self, package: AnalysisPackage) -> TrustedReportData:
        facts = [self._fact(item) for item in package.evidence]
        facts.extend(self._finding_fact(finding) for finding in package.deterministic_findings)
        evidence_charts = [
            self._chart(item) for item in package.evidence if self._is_numeric_comparison(item)
        ]
        finding_charts = [
            self._finding_chart(finding)
            for finding in package.deterministic_findings
            if finding.rule == "scan_ratio_change"
        ]
        charts = [*evidence_charts, *finding_charts]
        verification = [
            self._verification_query(package.target, item)
            for item in package.evidence
            if item.source.query
        ]
        chart_evidence_ids = {
            chart.id: [item.id]
            for chart, item in zip(
                evidence_charts,
                [item for item in package.evidence if self._is_numeric_comparison(item)],
                strict=True,
            )
        }
        chart_evidence_ids.update(
            {
                chart.id: finding.evidence_ids
                for chart, finding in zip(
                    finding_charts,
                    [
                        finding
                        for finding in package.deterministic_findings
                        if finding.rule == "scan_ratio_change"
                    ],
                    strict=True,
                )
            }
        )
        trusted = TrustedReportSection(
            facts=facts,
            charts=charts,
            verification=verification,
            chart_evidence_ids=chart_evidence_ids,
        )
        return TrustedReportData(sections={"default": trusted})

    @staticmethod
    def _label(name: str) -> str:
        return name.replace("_", " ").capitalize()

    @classmethod
    def _fact(cls, evidence: Evidence) -> ReportFact:
        value = evidence.value
        unit = evidence.unit or (value.get("unit") if isinstance(value, dict) else None)
        if isinstance(value, dict) and "before" in value and "after" in value:
            suffix = f" {unit}" if unit else ""
            if evidence.name == "query_plan" and value["before"] == value["after"]:
                text = f"Query plan remained {value['after']}."
            else:
                text = (
                    f"{cls._label(evidence.name)} changed from {value['before']}{suffix} "
                    f"to {value['after']}{suffix}."
                )
        else:
            if evidence.name == "connection_failures" and isinstance(value, dict):
                text = (
                    f"Connection failures were present ({value.get('count', 'unknown')} observed)."
                )
            elif evidence.name == "deployment" and isinstance(value, dict):
                parts = []
                for key in ("service", "version", "timestamp"):
                    if key in value and value[key] is not None:
                        parts.append(f"{key}={value[key]}")
                summary = "; ".join(parts) if parts else str(value)
                text = f"Deployment event: {summary}."
            else:
                text = f"{cls._label(evidence.name)}: {value}."
        return ReportFact(text=text, evidence_ids=[evidence.id], deterministic_finding_ids=[])

    @classmethod
    def _finding_fact(cls, finding) -> ReportFact:
        result = finding.result
        if finding.rule == "latency_percent_change":
            text = f"Latency increased by {result['percentIncrease']}%."
        elif finding.rule == "scan_ratio_change":
            text = f"Scan ratio changed from {result['before']} to {result['after']}."
        elif finding.rule == "connection_pressure":
            text = (
                f"Connection utilization changed from {result['beforePercent']}% "
                f"to {result['afterPercent']}%."
            )
        elif finding.rule == "query_plan_change":
            text = f"Query plan changed from {result['before']} to {result['after']}."
        elif finding.rule == "query_plan_stable":
            text = (
                f"Query plan remained {result['plan']}; scan-ratio change was "
                f"{result['scanRatioChangePercent']}%."
            )
        else:
            text = f"{cls._label(finding.rule)}: {result}."
        return ReportFact(text=text, evidence_ids=[], deterministic_finding_ids=[finding.id])

    @staticmethod
    def _is_numeric_comparison(evidence: Evidence) -> bool:
        value = evidence.value
        return (
            isinstance(value, dict)
            and "before" in value
            and "after" in value
            and isinstance(value["before"], (int, float))
            and isinstance(value["after"], (int, float))
        )

    @classmethod
    def _chart(cls, evidence: Evidence) -> ReportChart:
        value = evidence.value
        unit = evidence.unit or value.get("unit")
        chart_id = re.sub(r"[^a-z0-9]+", "-", evidence.name.lower()).strip("-")
        return ReportChart(
            id=chart_id,
            title=cls._label(evidence.name),
            type="bar",
            unit=unit,
            series=[
                ChartPoint(label="Before", value=value["before"]),
                ChartPoint(label="After", value=value["after"]),
            ],
        )

    @classmethod
    def _finding_chart(cls, finding) -> ReportChart:
        result = finding.result
        return ReportChart(
            id="scan-ratio",
            title="Scan ratio",
            type="bar",
            unit="examined / returned",
            series=[
                ChartPoint(label="Before", value=result["before"]),
                ChartPoint(label="After", value=result["after"]),
            ],
        )

    @classmethod
    def _verification_query(cls, target: str, evidence: Evidence) -> VerificationQuery:
        query = evidence.source.query or ""
        if evidence.source.system == "mock" and query.startswith("illustrative"):
            query = cls._mock_query(target, evidence.name)
        return VerificationQuery(
            system=evidence.source.system,
            query=query,
            label=cls._label(evidence.name),
            mode="illustrative" if evidence.source.system == "mock" else "actual",
            evidence_ids=[evidence.id],
        )

    @staticmethod
    def _mock_query(target: str, name: str) -> str:
        if name == "request_p95_ms":
            return (
                "histogram_quantile(0.95, sum by (le) "
                f'(rate(http_request_duration_seconds_bucket{{service="{target}"}}[5m])))'
            )
        if name in {"documents_examined", "documents_returned"}:
            return (
                'db.getSiblingDB("admin").system.profile.find({op: "query"})'
                ".sort({ts: -1}).limit(20)"
            )
        if name == "query_plan":
            return 'db.<database>.<collection>.find(<same filter>).explain("executionStats")'
        return "Run the corresponding read-only check for this observation."
