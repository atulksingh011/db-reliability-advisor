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


def _ai_unavailable(run: dict[str, Any] | None) -> bool:
    return bool(run and run.get("status") == "completed_with_fallback")


def _trusted_summary(report: dict[str, Any], ai_unavailable: bool) -> str:
    summary = report.get("summary", "")
    if ai_unavailable:
        for prefix in ("AI interpretation unavailable. ", "AI interpretation was unavailable. "):
            if summary.startswith(prefix):
                return summary[len(prefix) :]
    return summary


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


def _display_value(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _raw_observation(fact: dict[str, Any], package: dict[str, Any] | None) -> str:
    evidence_id = (fact.get("evidenceIds") or [None])[0]
    evidence = next(
        (item for item in (package or {}).get("evidence", []) if item.get("id") == evidence_id),
        None,
    )
    value = evidence.get("value") if evidence else None
    name = evidence.get("name") if evidence else None
    if isinstance(value, dict) and "before" in value and "after" in value:
        if name == "query_plan" and value["before"] == value["after"]:
            return f"remained {_display_value(value['after'])}"
        unit = evidence.get("unit") or value.get("unit")
        suffix = f" {unit}" if unit else ""
        return (
            f"{_display_value(value['before'])}{suffix} → "
            f"{_display_value(value['after'])}{suffix}"
        )
    return fact.get("text", "")


def _finding_rows(
    finding: dict[str, Any], package: dict[str, Any] | None
) -> list[dict[str, Any]]:
    result = finding.get("result") or {}
    evidence_ids = finding.get("evidenceIds") or []
    rule = finding.get("rule")
    if rule == "scan_ratio_change":
        return [
            {
                "signal": "Scan ratio",
                "observation": (
                    f"{_display_value(result.get('before'))} → "
                    f"{_display_value(result.get('after'))}"
                ),
                "evidence": evidence_ids,
            }
        ]
    if rule == "query_plan_change":
        return [
            {
                "signal": "Query plan",
                "observation": f"{result.get('before')} → {result.get('after')}",
                "evidence": evidence_ids,
            }
        ]
    if rule == "query_plan_stable":
        rows = []
        evidence_by_id = {
            item.get("id"): item for item in (package or {}).get("evidence", [])
        }
        for evidence_id in evidence_ids:
            evidence = evidence_by_id.get(evidence_id) or {}
            name = evidence.get("name")
            if name == "query_plan":
                rows.append(
                    {
                        "signal": "Query plan",
                        "observation": f"remained {result.get('plan')}",
                        "evidence": [evidence_id],
                    }
                )
            elif name == "scan_ratio":
                value = evidence.get("value") or {}
                rows.append(
                    {
                        "signal": "Scan ratio",
                        "observation": (
                            "remained approximately stable "
                            f"({_display_value(value.get('before'))} → "
                            f"{_display_value(value.get('after'))})"
                        ),
                        "evidence": [evidence_id],
                    }
                )
        return rows
    return []


def _evidence_rows(
    section: dict[str, Any],
    ids: list[str],
    package: dict[str, Any] | None = None,
    *,
    contradiction: bool = False,
) -> list[dict[str, Any]]:
    wanted = set(ids)
    facts = section.get("facts", [])
    findings = {
        finding.get("id"): finding
        for finding in (package or {}).get("deterministicFindings", [])
    }
    raw_facts = [fact for fact in facts if not fact.get("deterministicFindingIds")]
    rows = [
        {
            "signal": _evidence_label(evidence_ids[0], package)
            if evidence_ids
            else "Signal",
            "observation": _raw_observation(fact, package),
            "evidence": evidence_ids,
        }
        for fact in raw_facts
        if (evidence_ids := fact.get("evidenceIds", []))
        and wanted.intersection(evidence_ids)
    ]
    for fact in facts:
        for finding_id in fact.get("deterministicFindingIds", []):
            finding = findings.get(finding_id)
            if not finding or not wanted.intersection(finding.get("evidenceIds", [])):
                continue
            rule = finding.get("rule")
            preferred = rule in {"scan_ratio_change", "query_plan_change"}
            split_stable = contradiction and rule == "query_plan_stable"
            if not preferred and not split_stable:
                continue
            finding_evidence = set(finding.get("evidenceIds", []))
            rows = [row for row in rows if not finding_evidence.intersection(row["evidence"])]
            rows.extend(_finding_rows(finding, package))
            break
    unique_rows = []
    seen = set()
    for row in rows:
        key = (row["signal"], tuple(row["evidence"]), row["observation"])
        if key not in seen:
            seen.add(key)
            unique_rows.append(row)
    return unique_rows


def _limitation_group(value: str) -> str:
    normalized = value.casefold()
    if any(
        phrase in normalized
        for phrase in ("ai interpretation unavailable", "ai interpretation was unavailable")
    ):
        return "causation"
    if any(term in normalized for term in ("causation", "causal", "root cause")):
        return "causation"
    if any(
        term in normalized
        for term in ("client", "caller", "workload", "query origin", "tenant")
    ):
        return "workload_identity"
    if "query" in normalized and any(
        term in normalized for term in ("text", "collection", "signature")
    ):
        return "query_scope"
    if "mock" in normalized or ("production" in normalized and "telemetry" in normalized):
        return "mock_telemetry"
    return "unique:" + " ".join(normalized.split())


def _limitation_score(value: str, group: str) -> tuple[int, int]:
    normalized = value.casefold()
    if group == "ai_unavailable":
        return (2 if "root cause" in normalized else 1, len(value))
    if group == "mock_telemetry":
        return (2 if "mock" in normalized and "production" in normalized else 1, len(value))
    return (1, len(value))


def _unique(values: list[str]) -> list[str]:
    grouped: dict[str, str] = {}
    for value in values:
        group = _limitation_group(value)
        current = grouped.get(group)
        if current is None or _limitation_score(value, group) > _limitation_score(current, group):
            grouped[group] = value
    return list(grouped.values())


def report_page_model(
    report: dict[str, Any], run: dict[str, Any] | None = None, package: dict[str, Any] | None = None
) -> dict[str, Any]:
    ai_unavailable = _ai_unavailable(run)
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
            section,
            section.get("hypothesis", {}).get("contradictingEvidenceIds", []),
            package,
            contradiction=True,
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
        "ai_unavailable": ai_unavailable,
        "trusted_summary": _trusted_summary(report, ai_unavailable),
        "status_label": report.get("status", "unknown").replace("_", " "),
        "start_display": _display_time(window.get("startTime")),
        "end_display": _display_time(window.get("endTime")),
        "duration": _duration(window),
        "limitations": _unique(all_limitations),
        "root_path": "",
    }


def recent_analysis_views(
    reports: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    packages: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    run_by_id = {item.get("analysisId"): item for item in runs}
    views = []
    for report in reports:
        run = run_by_id.get(report.get("analysisId"))
        first = (report.get("sections") or [{}])[0]
        package = (packages or {}).get(report.get("analysisId")) or (run or {}).get("package")
        views.append(
            {
                "report": report,
                "mock_data": _mock(run),
                "status_label": report.get("status", "unknown").replace("_", " "),
                "start_display": _display_time((report.get("window") or {}).get("startTime")),
                "end_display": _display_time((report.get("window") or {}).get("endTime")),
                "duration": _duration(report.get("window") or {}),
                "condition": _condition(package)[0],
                "metrics": select_metrics(first, package),
            }
        )
    return views
