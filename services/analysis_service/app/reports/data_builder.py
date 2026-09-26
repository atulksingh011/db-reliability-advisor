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


@dataclass(frozen=True)
class TrustedReportData:
    sections: dict[str, TrustedReportSection]


class TrustedReportDataBuilder:
    """Translate Contract B into report-safe values without calling AI or storage."""

    def build(self, package: AnalysisPackage) -> TrustedReportData:
        facts = [self._fact(item) for item in package.evidence]
        facts.extend(self._finding_fact(finding) for finding in package.deterministic_findings)
        charts = [
            self._chart(item)
            for item in package.evidence
            if self._is_numeric_comparison(item)
        ]
        verification = [
            VerificationQuery(
                system=item.source.system,
                query=item.source.query,
                label=self._label(item.name),
            )
            for item in package.evidence
            if item.source.system in {"prometheus", "loki"} and item.source.query
        ]
        trusted = TrustedReportSection(
            facts=facts,
            charts=charts,
            verification=verification,
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
            text = (
                f"{cls._label(evidence.name)} changed from {value['before']}{suffix} "
                f"to {value['after']}{suffix}."
            )
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
