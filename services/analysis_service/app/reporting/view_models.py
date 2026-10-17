"""Presentation-only models for the Advisor HTML surfaces."""

from __future__ import annotations

from datetime import datetime
from typing import Any

RULE_LABELS = {
    "latency_percent_change": "Request latency regression",
    "scan_ratio_change": "Query scan efficiency regression",
    "query_plan_change": "Query plan change",
    "query_plan_stable": "Query plan remained stable",
    "connection_pressure": "Connection Pressure",
    "query_scan_ratio_window": "Query scan observations",
}

CHART_LABELS = {
    "request-p95-ms": "Request p95",
    "connection-utilization-percent": "Connection utilization",
    "request-error-rate-percent": "Request error rate",
    "scan-ratio": "Scan ratio",
    "documents-examined": "Documents examined",
    "documents-returned": "Documents returned",
    "query-plan": "Query plan",
}

EVIDENCE_LABELS = {
    "deployment": "Deployment event",
    "request_p95_ms": "Request p95",
    "documents_examined": "Documents examined",
    "documents_returned": "Documents returned",
    "query_plan": "Query plan",
    "scan_ratio": "Scan ratio",
    "connection_utilization_percent": "Connection utilization",
    "request_error_rate_percent": "Request error rate",
    "connection_failures": "Connection failures",
}


def _iso(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _display_time(value: Any) -> str:
    parsed = _iso(value)
    return parsed.strftime("%Y-%m-%d %H:%M UTC") if parsed else str(value or "Unknown")


def _duration(window: dict[str, Any]) -> str:
    start, end = _iso(window.get("startTime")), _iso(window.get("endTime"))
    if not start or not end:
        return "Duration unavailable"
    seconds = max(0, int((end - start).total_seconds()))
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes}m {remainder}s" if remainder else f"{minutes}m"


def _mock(run: dict[str, Any] | None) -> bool:
    return bool(run and run.get("fixtureName"))


def _condition(package: dict[str, Any] | None) -> tuple[str, str]:
    findings = (package or {}).get("deterministicFindings") or []
    for finding in findings:
        label = RULE_LABELS.get(finding.get("rule"))
        if label:
            return label, "Trusted deterministic finding from the analysis evidence."
    return (
        "Observed condition",
        "Trusted facts are available; no named deterministic condition was established.",
    )


def _format_metric(chart: dict[str, Any]) -> dict[str, Any]:
    series = chart.get("series") or []
    return {
        "label": CHART_LABELS.get(chart.get("id"), chart.get("title", "Signal")),
        "before": series[0].get("value") if len(series) > 0 else None,
        "after": series[1].get("value") if len(series) > 1 else None,
        "unit": chart.get("unit"),
        "id": chart.get("id"),
    }


def _trusted_query_plan_metric(package: dict[str, Any] | None) -> dict[str, Any] | None:
    evidence = next(
        (item for item in (package or {}).get("evidence", []) if item.get("name") == "query_plan"),
        None,
    )
    value = evidence.get("value") if evidence else None
    if not isinstance(value, dict) or "before" not in value or "after" not in value:
        return None
    return {
        "id": "query-plan",
        "title": "Query plan",
        "unit": None,
        "series": [{"value": value["before"]}, {"value": value["after"]}],
    }


def select_metrics(
    section: dict[str, Any], package: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Select up to three trusted charts by stable signal IDs, never by AI prose."""
    charts = {chart.get("id"): chart for chart in section.get("charts", [])}
    trusted_query_plan = _trusted_query_plan_metric(package)
    if trusted_query_plan and "query-plan" not in charts:
        charts["query-plan"] = trusted_query_plan
    if {
        "connection-utilization-percent",
        "request-error-rate-percent",
    }.intersection(charts):
        # Preserve the accepted Connection Pressure signal ordering.
        preferred = [
            "request-p95-ms",
            "connection-utilization-percent",
            "request-error-rate-percent",
            "scan-ratio",
            "documents-examined",
            "documents-returned",
            "query-plan",
        ]
    else:
        preferred = [
            "request-p95-ms",
            "scan-ratio",
            "query-plan",
            "documents-examined",
            "documents-returned",
        ]
    selected = [charts[item] for item in preferred if item in charts]
    selected.extend(chart for key, chart in charts.items() if key not in preferred)
    return [_format_metric(chart) for chart in selected[:3]]


def _evidence_label(evidence_id: str, package: dict[str, Any] | None) -> str:
    evidence = next(
        (item for item in (package or {}).get("evidence", []) if item.get("id") == evidence_id),
        None,
    )
    name = evidence.get("name") if evidence else None
    if name:
        return EVIDENCE_LABELS.get(name, name.replace("_", " ").title())
    return "Signal"


def _evidence_rows(
    section: dict[str, Any], ids: list[str], package: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    wanted = set(ids)
    rows = []
    for fact in section.get("facts", []):
        evidence_ids = fact.get("evidenceIds", [])
        if wanted.intersection(evidence_ids):
            rows.append(
                {
                    "signal": _evidence_label(evidence_ids[0], package)
                    if evidence_ids
                    else "Signal",
                    "observation": fact.get("text", ""),
                    "evidence": evidence_ids,
                }
            )
    return rows


def _unique(values: list[str]) -> list[str]:
    result, seen = [], set()
    for value in values:
        normalized = " ".join(value.split()).casefold()
        if normalized not in seen:
            seen.add(normalized)
            result.append(value)
    return result


def report_page_model(
    report: dict[str, Any], run: dict[str, Any] | None = None, package: dict[str, Any] | None = None
) -> dict[str, Any]:
    sections = []
    all_limitations = list(report.get("limitations", []))
    for raw in report.get("sections", []):
        section = dict(raw)
        section["metrics"] = select_metrics(section, package)
        section["condition_title"], section["condition_description"] = _condition(package)
        section["supporting_rows"] = _evidence_rows(
            section, section.get("hypothesis", {}).get("supportingEvidenceIds", []), package
        )
        section["contradicting_rows"] = _evidence_rows(
            section, section.get("hypothesis", {}).get("contradictingEvidenceIds", []), package
        )
        section["checks"] = [
            {"action": item.get("description", ""), "purpose": item.get("purpose")}
            if isinstance(item, dict)
            else {"action": item, "purpose": None}
            for item in section.get("recommendedChecks", [])
        ]
        all_limitations.extend(section.get("limitations", []))
        sections.append(section)
    window = report.get("window", {})
    return {
        "report": report,
        "sections": sections,
        "mock_data": _mock(run),
        "status_label": report.get("status", "unknown").replace("_", " "),
        "start_display": _display_time(window.get("startTime")),
        "end_display": _display_time(window.get("endTime")),
        "duration": _duration(window),
        "limitations": _unique(all_limitations),
        "root_path": "",
    }


def recent_analysis_views(
    reports: list[dict[str, Any]], runs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    run_by_id = {item.get("analysisId"): item for item in runs}
    views = []
    for report in reports:
        run = run_by_id.get(report.get("analysisId"))
        first = (report.get("sections") or [{}])[0]
        views.append(
            {
                "report": report,
                "mock_data": _mock(run),
                "status_label": report.get("status", "unknown").replace("_", " "),
                "start_display": _display_time((report.get("window") or {}).get("startTime")),
                "end_display": _display_time((report.get("window") or {}).get("endTime")),
                "duration": _duration(report.get("window") or {}),
                "condition": _condition((run or {}).get("package"))[0]
                if run
                else "Observed condition",
                "metrics": select_metrics(first),
            }
        )
    return views
