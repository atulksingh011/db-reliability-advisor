"""
Evidence Kinds Builder for DBADV-02.

Constructs evidence kinds (metric_comparison, query_comparison, query_plan, etc.)
from normalized evidence for deterministic analysis.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from uuid import uuid4

from ...contracts.models import (
    AnalysisRequest,
    Evidence,
    EvidenceObservationWindow,
    EvidenceSource,
)
from ..normalizer import (
    NormalizedLogObservation,
    NormalizedMetric,
    NormalizedMongoMetadata,
)


def build_evidence_kinds(
    metrics: list[NormalizedMetric],
    logs: list[NormalizedLogObservation],
    metadata: list[NormalizedMongoMetadata],
    events: list[NormalizedLogObservation],
    request: AnalysisRequest,
) -> list[Evidence]:
    """
    Build evidence kinds for deterministic analysis.

    Creates evidence items of kinds:
    - metric_comparison: Before/after metric comparisons
    - query_comparison: Query efficiency comparisons (documents examined/returned)
    - query_plan: Query plan changes (IXSCAN -> COLLSCAN)
    - metadata: MongoDB metadata (indexes, connection limit, version)
    - event: Context events (deployments, restarts, alerts)
    - metric_window: Window-based metrics without before/after
    - query_window: Query metrics without before/after

    Args:
        metrics: Normalized metrics from Prometheus
        logs: Normalized logs from Loki
        metadata: Normalized metadata from MongoDB
        events: Discovered context events
        request: Analysis request

    Returns:
        List of Evidence items ready for deterministic analysis
    """
    evidence = []

    # Build each evidence kind
    evidence.extend(_build_metric_comparisons(metrics, request))
    split_time = _change_event_time(events)
    scenario_id = _change_event_scenario_id(events, split_time)
    evidence.extend(_build_query_comparisons(logs, request, split_time, scenario_id))
    evidence.extend(_build_query_plans(logs, request, split_time, scenario_id))
    evidence.extend(_build_connection_failures(logs, request))
    evidence.extend(_build_metadata_evidence(metadata, request))
    evidence.extend(_build_event_evidence(events, request))
    evidence.extend(_build_metric_windows(metrics, request))
    evidence.extend(_build_query_windows(logs, request, split_time))

    return evidence


def _build_metric_comparisons(
    metrics: list[NormalizedMetric], request: AnalysisRequest
) -> list[Evidence]:
    """Build metric_comparison evidence from before/after metrics."""
    evidence = []

    for metric in metrics:
        if isinstance(metric.value, dict) and "before" in metric.value and "after" in metric.value:
            evidence.append(
                Evidence(
                    id=str(uuid4()),  # Will be reassigned later
                    kind="metric_comparison",
                    name=metric.name,
                    value=metric.value,
                    unit=metric.unit,
                    source=EvidenceSource(system=metric.source, query=metric.source_query),
                    observation_window=EvidenceObservationWindow(
                        start_time=request.start_time,
                        end_time=request.end_time,
                    ),
                    timestamp=None,
                )
            )

    return evidence


def _change_event_time(events: list[NormalizedLogObservation]) -> datetime | None:
    """Use the earliest meaningful change marker as the comparison boundary."""
    candidates = [
        event.timestamp
        for event in events
        if event.timestamp is not None
        and isinstance(event.value, dict)
        and event.value.get("event") in {"deployment", "restart", "scenario_marker"}
    ]
    return min(candidates) if candidates else None


def _change_event_scenario_id(
    events: list[NormalizedLogObservation], split_time: datetime | None
) -> str | None:
    for event in events:
        if (
            event.timestamp == split_time
            and isinstance(event.value, dict)
            and isinstance(event.value.get("scenarioId"), str)
        ):
            return event.value["scenarioId"]
    return None


def _slow_operations(
    logs: list[NormalizedLogObservation], scenario_id: str | None = None
) -> list[NormalizedLogObservation]:
    operations = [
        log for log in logs if log.name == "mongodb_slow_operation" and isinstance(log.value, dict)
    ]
    if scenario_id is not None:
        return [log for log in operations if log.value.get("scenarioId") == scenario_id]
    return operations


def _average(logs: list[NormalizedLogObservation], field: str) -> float | None:
    values = []
    for log in logs:
        value = log.value.get(field)
        if isinstance(value, (int, float)):
            values.append(float(value))
    return sum(values) / len(values) if values else None


def _source_query(logs: list[NormalizedLogObservation]) -> str:
    return logs[0].source_query if logs else ""


def _build_query_comparisons(
    logs: list[NormalizedLogObservation],
    request: AnalysisRequest,
    split_time: datetime | None,
    scenario_id: str | None,
) -> list[Evidence]:
    """Build query_comparison evidence from slow-operation logs."""
    operations = _slow_operations(logs, scenario_id)
    if split_time is None:
        return []
    before = [log for log in operations if log.timestamp and log.timestamp < split_time]
    after = [log for log in operations if log.timestamp and log.timestamp >= split_time]
    if not before or not after:
        return []

    evidence = []
    for field, name in (
        ("documentsExamined", "documents_examined"),
        ("documentsReturned", "documents_returned"),
    ):
        before_value = _average(before, field)
        after_value = _average(after, field)
        if before_value is None or after_value is None:
            continue
        evidence.append(
            Evidence(
                id=str(uuid4()),
                kind="query_comparison",
                name=name,
                value={"before": before_value, "after": after_value},
                source=EvidenceSource(system="loki", query=_source_query(operations)),
                observation_window=EvidenceObservationWindow(
                    start_time=request.start_time,
                    end_time=request.end_time,
                ),
            )
        )
    return evidence


def _build_query_plans(
    logs: list[NormalizedLogObservation],
    request: AnalysisRequest,
    split_time: datetime | None,
    scenario_id: str | None,
) -> list[Evidence]:
    """Build query_plan evidence from slow-operation logs."""
    operations = _slow_operations(logs, scenario_id)
    if split_time is None:
        return []
    before = [log for log in operations if log.timestamp and log.timestamp < split_time]
    after = [log for log in operations if log.timestamp and log.timestamp >= split_time]

    def dominant_plan(items: list[NormalizedLogObservation]) -> str | None:
        plans = [log.value.get("planSummary") or log.value.get("plan_summary") for log in items]
        plans = [plan for plan in plans if isinstance(plan, str) and plan]
        return Counter(plans).most_common(1)[0][0] if plans else None

    before_plan = dominant_plan(before)
    after_plan = dominant_plan(after)
    if before_plan is None or after_plan is None:
        return []
    return [
        Evidence(
            id=str(uuid4()),
            kind="query_plan",
            name="query_plan",
            value={"before": before_plan, "after": after_plan},
            source=EvidenceSource(system="loki", query=_source_query(operations)),
            observation_window=EvidenceObservationWindow(
                start_time=request.start_time,
                end_time=request.end_time,
            ),
        )
    ]


def _build_metadata_evidence(
    metadata: list[NormalizedMongoMetadata], request: AnalysisRequest
) -> list[Evidence]:
    """Build metadata evidence from MongoDB metadata."""
    evidence = []

    for meta in metadata:
        evidence.append(
            Evidence(
                id=str(uuid4()),
                kind="metadata",
                name=meta.name,
                value=meta.value,
                unit=meta.unit,
                source=EvidenceSource(system=meta.source, query=meta.source_query),
                observation_window=EvidenceObservationWindow(
                    start_time=request.start_time,
                    end_time=request.end_time,
                ),
                timestamp=meta.timestamp,
            )
        )

    return evidence


def _build_connection_failures(
    logs: list[NormalizedLogObservation], request: AnalysisRequest
) -> list[Evidence]:
    failures = [log for log in logs if log.name == "connection_failure"]
    if not failures:
        return []
    return [
        Evidence(
            id=str(uuid4()),
            kind="event",
            name="connection_failures",
            value={"present": True, "count": len(failures)},
            source=EvidenceSource(system="loki", query=_source_query(failures)),
            observation_window=EvidenceObservationWindow(
                start_time=request.start_time,
                end_time=request.end_time,
            ),
        )
    ]


def _build_event_evidence(
    events: list[NormalizedLogObservation], request: AnalysisRequest
) -> list[Evidence]:
    """Build event evidence from context events."""
    evidence = []

    for event in events:
        observation_window = None
        if event.start_time is not None and event.end_time is not None:
            observation_window = EvidenceObservationWindow(
                start_time=event.start_time,
                end_time=event.end_time,
            )
        evidence.append(
            Evidence(
                id=str(uuid4()),
                kind="event",
                name=event.name,
                value=event.value,
                unit=event.unit,
                source=EvidenceSource(system=event.source, query=event.source_query),
                observation_window=observation_window,
                timestamp=event.timestamp,
            )
        )

    return evidence


def _build_metric_windows(
    metrics: list[NormalizedMetric], request: AnalysisRequest
) -> list[Evidence]:
    """Build metric_window evidence for window-based metrics."""
    evidence = []

    for metric in metrics:
        # Only create window evidence for metrics that aren't already comparisons
        if not (
            isinstance(metric.value, dict) and "before" in metric.value and "after" in metric.value
        ):
            evidence.append(
                Evidence(
                    id=str(uuid4()),
                    kind="metric_window",
                    name=metric.name,
                    value=metric.value,
                    unit=metric.unit,
                    source=EvidenceSource(system=metric.source, query=metric.source_query),
                    observation_window=EvidenceObservationWindow(
                        start_time=request.start_time,
                        end_time=request.end_time,
                    ),
                    timestamp=metric.timestamp,
                )
            )

    return evidence


def _build_query_windows(
    logs: list[NormalizedLogObservation],
    request: AnalysisRequest,
    split_time: datetime | None,
) -> list[Evidence]:
    """Build query_window evidence for query metrics without before/after."""
    if split_time is not None:
        return []
    operations = _slow_operations(logs)
    if not operations:
        return []
    activity_values = {
        "operationCount": len(operations),
        "averageDocumentsExamined": _average(operations, "documentsExamined"),
        "averageDocumentsReturned": _average(operations, "documentsReturned"),
    }
    evidence = [
        Evidence(
            id=str(uuid4()),
            kind="query_window",
            name="query_activity",
            value={key: value for key, value in activity_values.items() if value is not None},
            source=EvidenceSource(system="loki", query=_source_query(operations)),
            observation_window=EvidenceObservationWindow(
                start_time=request.start_time,
                end_time=request.end_time,
            ),
        )
    ]
    plans = [log.value.get("planSummary") or log.value.get("plan_summary") for log in operations]
    plans = [plan for plan in plans if isinstance(plan, str) and plan]
    if plans:
        plan_counts = Counter(plans)
        evidence.append(
            Evidence(
                id=str(uuid4()),
                kind="query_plan",
                name="query_plan",
                value={
                    "window": plan_counts.most_common(1)[0][0],
                    "observedPlans": sorted(plan_counts),
                },
                source=EvidenceSource(system="loki", query=_source_query(operations)),
                observation_window=EvidenceObservationWindow(
                    start_time=request.start_time,
                    end_time=request.end_time,
                ),
            )
        )
    ratios = []
    for log in operations:
        examined = log.value.get("documentsExamined")
        returned = log.value.get("documentsReturned")
        if isinstance(examined, (int, float)) and isinstance(returned, (int, float)):
            ratios.append(float(examined) / max(float(returned), 1.0))
    if ratios:
        evidence.append(
            Evidence(
                id=str(uuid4()),
                kind="query_window",
                name="scan_ratio",
                value={
                    "min": min(ratios),
                    "max": max(ratios),
                    "average": sum(ratios) / len(ratios),
                },
                source=EvidenceSource(system="loki", query=_source_query(operations)),
                observation_window=EvidenceObservationWindow(
                    start_time=request.start_time,
                    end_time=request.end_time,
                ),
            )
        )
    return evidence
