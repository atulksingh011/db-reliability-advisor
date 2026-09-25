from datetime import UTC, datetime

import httpx

from services.analysis_service.app.adapters.base import CollectedEvidence
from services.analysis_service.app.adapters.loki import LokiAdapter
from services.analysis_service.app.adapters.mongodb import MongoMetadataAdapter
from services.analysis_service.app.adapters.multi_source import MultiSourceAdapter
from services.analysis_service.app.adapters.prometheus import PrometheusAdapter
from services.analysis_service.app.contracts.models import (
    AnalysisRequest,
    Evidence,
    EvidenceSource,
)


def make_request() -> AnalysisRequest:
    return AnalysisRequest(
        target="orders-api",
        start_time=datetime(2026, 9, 20, 10, tzinfo=UTC),
        end_time=datetime(2026, 9, 20, 10, 10, tzinfo=UTC),
    )


def test_prometheus_collects_project_metrics_as_before_after_comparison(monkeypatch) -> None:
    request = make_request()
    midpoint_ts = (request.start_time + (request.end_time - request.start_time) / 2).timestamp()
    queries = []

    def fake_get(url, params, timeout):
        query = params["query"]
        queries.append(query)
        is_latency = "histogram_quantile" in query
        is_connections = "mongodb_ss_connections" in query
        is_before = params["time"] == midpoint_ts
        latency_values = {True: "0.2", False: "1.0"}
        error_rate_values = {True: "0.0", False: "0.125"}
        connection_values = {True: "25", False: "92"}
        value = (
            latency_values[is_before]
            if is_latency
            else connection_values[is_before]
            if is_connections
            else error_rate_values[is_before]
        )

        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={"status": "success", "data": {"result": [{"value": ["1", value]}]}},
        )

    monkeypatch.setattr("services.analysis_service.app.adapters.prometheus.httpx.get", fake_get)
    collected = PrometheusAdapter("http://prometheus").collect(
        request,
        comparison_time=request.start_time + (request.end_time - request.start_time) / 2,
    )

    assert len(collected.evidence) == 3
    latency, error_rate, connections = collected.evidence
    assert latency.name == "request_p95_ms"
    assert latency.kind == "metric_comparison"
    assert latency.value == {"before": 200.0, "after": 1000.0}
    assert latency.unit == "ms"
    assert error_rate.name == "error_rate"
    assert error_rate.kind == "metric_comparison"
    assert error_rate.value == {"before": 0.0, "after": 0.125}
    assert error_rate.unit == "ratio"
    assert connections.name == "connection_utilization_percent"
    assert connections.value == {"before": 25.0, "after": 92.0}
    assert connections.unit == "percent"
    assert all(item.source.system == "prometheus" for item in collected.evidence)
    assert all("before:" not in item.source.query for item in collected.evidence)
    assert len(queries) == 6
    assert all(
        ("orders_api_" in query and 'job="orders-api"' in query)
        or ("mongodb_ss_connections" in query and 'job="mongodb-exporter"' in query)
        for query in queries
    )


def test_prometheus_uses_one_full_window_query_without_change_event(monkeypatch) -> None:
    request = make_request()
    calls = []

    def fake_get(url, params, timeout):
        calls.append(params)
        value = "0.25" if "histogram_quantile" in params["query"] else "0.5"
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={"status": "success", "data": {"result": [{"value": ["1", value]}]}},
        )

    monkeypatch.setattr("services.analysis_service.app.adapters.prometheus.httpx.get", fake_get)
    collected = PrometheusAdapter("http://prometheus").collect(request)

    assert len(calls) == 3
    assert all(call["time"] == request.end_time.timestamp() for call in calls)
    assert all(
        "[600s]" in call["query"] for call in calls if "mongodb_ss_connections" not in call["query"]
    )
    assert [item.kind for item in collected.evidence] == ["metric_window"] * 3
    assert collected.evidence[0].value == 250.0
    assert all(
        item.observation_window.start_time == request.start_time for item in collected.evidence
    )


def test_prometheus_records_unavailability_without_raising(monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("Prometheus is unavailable")

    monkeypatch.setattr("services.analysis_service.app.adapters.prometheus.httpx.get", unavailable)
    collected = PrometheusAdapter("http://prometheus").collect(make_request())

    assert collected.evidence == []
    assert len(collected.missing_evidence) == 3
    assert all("Failed to collect" in item for item in collected.missing_evidence)


def test_loki_uses_valid_queries_and_preserves_sanitized_provenance(monkeypatch) -> None:
    queries = []
    timestamp_ns = str(int(datetime(2026, 9, 20, 10, 5, tzinfo=UTC).timestamp() * 1_000_000_000))
    response_data = {
        "status": "success",
        "data": {
            "result": [
                {
                    "stream": {},
                    "values": [
                        [
                            timestamp_ns,
                            '{"event":"deployment","service":"orders-api",'
                            '"message":"email=person@example.com"}',
                        ]
                    ],
                }
            ]
        },
    }

    def fake_get(url, params, timeout):
        queries.append(params["query"])
        data = {"status": "success", "data": {"result": []}}
        if "event=~" in params["query"]:
            data = response_data
        return httpx.Response(200, request=httpx.Request("GET", url), json=data)

    monkeypatch.setattr("services.analysis_service.app.adapters.loki.httpx.get", fake_get)
    collected = LokiAdapter("http://loki").collect(make_request())

    assert len(collected.evidence) == 1
    assert all(item.source.system == "loki" for item in collected.evidence)
    assert [item.source.query for item in collected.evidence] == [queries[1]]
    assert 'msg="Slow query"' in queries[0]
    assert "event=~" in queries[1]
    assert "connection" in queries[2]
    assert all(", namespace" not in query for query in queries)
    assert collected.evidence[0].value["message"] == "email=[REDACTED]"
    assert collected.evidence[0].timestamp == datetime(2026, 9, 20, 10, 5, tzinfo=UTC)
    assert collected.evidence[0].observation_window.start_time == make_request().start_time


def test_loki_normalizes_mongodb_slow_operation_fields() -> None:
    normalized = LokiAdapter._normalize_slow_operation(
        {
            "attr": {
                "ns": "reliability_demo.orders",
                "command": {"find": "orders"},
                "durationMillis": 42,
                "docsExamined": 500,
                "nreturned": 5,
                "keysExamined": 5,
                "planSummary": "IXSCAN",
            }
        }
    )

    assert normalized == {
        "namespace": "reliability_demo.orders",
        "operation": "find",
        "durationMs": 42,
        "documentsExamined": 500,
        "documentsReturned": 5,
        "keysExamined": 5,
        "planSummary": "IXSCAN",
    }


def test_mongodb_uses_supported_list_indexes_and_tolerates_server_status_denial(
    monkeypatch,
) -> None:
    class FakeCollection:
        def list_indexes(self):
            return [{"name": "_id_", "key": {"_id": 1}}]

    class FakeDatabase:
        def __getitem__(self, name):
            assert name == "orders"
            return FakeCollection()

        def command(self, name):
            if name == "serverStatus":
                raise PermissionError("not authorized")
            return {"version": "8.0.0"}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get_default_database(self):
            return FakeDatabase()

    monkeypatch.setattr(
        "services.analysis_service.app.adapters.mongodb.MongoClient",
        lambda uri: FakeClient(),
    )

    collected = MongoMetadataAdapter("mongodb://example/reliability_demo").collect(make_request())

    assert [item.name for item in collected.evidence] == ["indexes", "version"]
    assert any("connection limit" in item for item in collected.missing_evidence)


def test_multi_source_collection_preserves_partial_failures() -> None:
    class AvailableSource:
        def collect(self, request, fixture_name=None):
            return CollectedEvidence(evidence=[], missing_evidence=["No source data"])

    class FailedSource:
        def collect(self, request, fixture_name=None):
            raise RuntimeError("source unavailable")

    collected = MultiSourceAdapter([AvailableSource(), FailedSource()]).collect(make_request())

    assert collected.evidence == []
    assert "No source data" in collected.missing_evidence
    assert any("FailedSource" in item for item in collected.missing_evidence)


def test_multi_source_aligns_prometheus_to_discovered_deployment() -> None:
    deployment_time = datetime(2026, 9, 20, 10, 4, tzinfo=UTC)

    class ContextSource:
        def collect(self, request, fixture_name=None):
            return CollectedEvidence(
                evidence=[
                    Evidence(
                        id="raw-event",
                        kind="event",
                        name="context_event",
                        value={"event": "deployment", "service": "orders-api"},
                        source=EvidenceSource(system="loki", query="deployment query"),
                        timestamp=deployment_time,
                    )
                ],
                missing_evidence=[],
            )

    class CapturingPrometheus(PrometheusAdapter):
        def __init__(self):
            super().__init__("http://prometheus")
            self.comparison_time = None

        def collect(self, request, fixture_name=None, comparison_time=None):
            self.comparison_time = comparison_time
            return CollectedEvidence(evidence=[], missing_evidence=[])

    prometheus = CapturingPrometheus()
    MultiSourceAdapter([prometheus, ContextSource()]).collect(make_request())

    assert prometheus.comparison_time == deployment_time
