import math
from datetime import datetime
from uuid import uuid4

import httpx

from ..contracts.models import (
    AnalysisRequest,
    Evidence,
    EvidenceObservationWindow,
    EvidenceSource,
)
from .base import CollectedEvidence


class PrometheusAdapter:
    """
    Adapter for collecting metrics from Prometheus.
    Implements: Fetch and normalize Prometheus metrics (request p95, error rate).
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def ready(self) -> bool:
        """Check if Prometheus is ready."""
        try:
            response = httpx.get(f"{self.base_url}/-/ready", timeout=2)
            return response.is_success
        except httpx.RequestError:
            return False

    @staticmethod
    def _duration_literal(seconds: float) -> str:
        """Clamp to a minimum so the rate() range vector always has samples."""
        return f"{max(round(seconds), 1)}s"

    @staticmethod
    def _query(metric_name: str, escaped_target: str, duration: str) -> str:
        if metric_name == "request_p95_ms":
            return (
                "histogram_quantile(0.95, "
                "sum by (le) (rate(orders_api_request_duration_seconds_bucket"
                f'{{job="{escaped_target}"}}[{duration}])))'
            )
        if metric_name == "connection_utilization_percent":
            return (
                '100 * sum(mongodb_ss_connections{job="mongodb-exporter",conn_type="current"}) '
                '/ clamp_min(sum(mongodb_ss_connections{job="mongodb-exporter",'
                'conn_type=~"current|available"}), 1)'
            )
        return (
            "(sum(rate(orders_api_requests_total"
            f'{{job="{escaped_target}",status=~"5.."}}[{duration}])) or vector(0)) '
            "/ clamp_min(sum(rate(orders_api_requests_total"
            f'{{job="{escaped_target}"}}[{duration}])), 1e-12)'
        )

    def _instant_value(self, promql: str, query_time: float) -> float | None:
        """Return the scalar value for a PromQL instant query, or None if no data."""
        response = httpx.get(
            f"{self.base_url}/api/v1/query",
            params={"query": promql, "time": query_time},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if data["status"] != "success":
            raise ValueError(f"Prometheus query failed: {data}")

        result = data["data"]["result"]
        if not result:
            return None

        value_str = result[0]["value"][1]
        try:
            value = float(value_str)
        except ValueError as err:
            raise ValueError(f"Invalid value from Prometheus: {value_str}") from err
        if not math.isfinite(value):
            raise ValueError(f"Non-finite value from Prometheus: {value_str}")
        return value

    def collect(
        self,
        request: AnalysisRequest,
        fixture_name: str | None = None,
        comparison_time: datetime | None = None,
    ) -> CollectedEvidence:
        """
        Collect bounded Prometheus comparisons split at a discovered change event,
        or at the midpoint when no change event is available.
        Returns CollectedEvidence with list of Evidence objects.
        """
        evidence_list = []
        missing_evidence = []

        # If fixture_name is provided, we could load mock data for testing.
        # For simplicity, we skip fixture loading in this implementation.
        # In a real test environment, you would load from fixture files.
        # mock mode uses MockAdapter instead
        if fixture_name:
            # For now, return empty evidence when fixture mode is requested.
            # This allows tests to proceed without actual Prometheus.
            return CollectedEvidence(evidence=[], missing_evidence=[])

        target = request.target
        escaped_target = target.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

        midpoint = comparison_time
        if midpoint is not None and not request.start_time < midpoint < request.end_time:
            midpoint = None
        if midpoint is None:
            duration = self._duration_literal(
                (request.end_time - request.start_time).total_seconds()
            )
        else:
            before_duration = self._duration_literal(
                (midpoint - request.start_time).total_seconds()
            )
            after_duration = self._duration_literal((request.end_time - midpoint).total_seconds())

        for metric_name in (
            "request_p95_ms",
            "error_rate",
            "connection_utilization_percent",
        ):
            try:
                if midpoint is None:
                    query = self._query(metric_name, escaped_target, duration)
                    value = self._instant_value(query, request.end_time.timestamp())
                    if value is None:
                        missing_evidence.append(f"No data for {metric_name}")
                        continue
                    unit = self._unit(metric_name)
                    if metric_name == "request_p95_ms":
                        value *= 1000.0
                    evidence = Evidence(
                        id=str(uuid4()),
                        kind="metric_window",
                        name=metric_name,
                        value=value,
                        unit=unit,
                        source=EvidenceSource(system="prometheus", query=query),
                        observation_window=EvidenceObservationWindow(
                            start_time=request.start_time,
                            end_time=request.end_time,
                        ),
                    )
                else:
                    before_query = self._query(metric_name, escaped_target, before_duration)
                    after_query = self._query(metric_name, escaped_target, after_duration)
                    before_value = self._instant_value(before_query, midpoint.timestamp())
                    after_value = self._instant_value(after_query, request.end_time.timestamp())
                    if before_value is None or after_value is None:
                        missing_evidence.append(f"No data for {metric_name}")
                        continue
                    if metric_name == "request_p95_ms":
                        before_value *= 1000.0
                        after_value *= 1000.0
                    evidence = Evidence(
                        id=str(uuid4()),
                        kind="metric_comparison",
                        name=metric_name,
                        value={"before": before_value, "after": after_value},
                        unit=self._unit(metric_name),
                        source=EvidenceSource(system="prometheus", query=before_query),
                        observation_window=EvidenceObservationWindow(
                            start_time=request.start_time,
                            end_time=request.end_time,
                        ),
                    )
                evidence_list.append(evidence)

            except (httpx.RequestError, ValueError, KeyError, IndexError) as exc:
                # Record failure for this metric.
                missing_evidence.append(f"Failed to collect {metric_name} from Prometheus: {exc}")
                continue

        return CollectedEvidence(
            evidence=evidence_list,
            missing_evidence=missing_evidence,
        )

    @staticmethod
    def _unit(metric_name: str) -> str:
        if metric_name == "request_p95_ms":
            return "ms"
        if metric_name == "connection_utilization_percent":
            return "percent"
        return "ratio"
