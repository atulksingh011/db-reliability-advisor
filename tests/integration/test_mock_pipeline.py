from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from services.analysis_service.app.adapters.base import CollectedEvidence
from services.analysis_service.app.adapters.mock import MockAdapter
from services.analysis_service.app.ai.base import AIProvider
from services.analysis_service.app.ai.mock_provider import MockAIProvider
from services.analysis_service.app.analyzers.deterministic import DeterministicAnalyzer
from services.analysis_service.app.api import analyses
from services.analysis_service.app.config import Settings
from services.analysis_service.app.contracts.models import AnalysisRequest
from services.analysis_service.app.evidence.builder import EvidenceBuilder
from services.analysis_service.app.main import create_app
from services.analysis_service.app.orchestration.pipeline import AnalysisPipeline
from services.analysis_service.app.reporting.renderer import TEMPLATES
from services.analysis_service.app.storage.database import (
    create_database_engine,
    initialize_database,
)
from services.analysis_service.app.storage.models import (
    AIAttempt,
    AnalysisResult,
    AnalysisRun,
    DeterministicResult,
    EvidenceSnapshot,
)
from services.analysis_service.app.storage.repository import AnalysisRepository


class SnapshotCheckingProvider(MockAIProvider):
    def __init__(self, repository: AnalysisRepository) -> None:
        self.repository = repository

    def analyze(self, package):
        snapshot = self.repository.get_package(package.analysis_id)
        assert snapshot is not None
        package_payload = package.model_dump(mode="json", by_alias=True)
        assert snapshot["evidence"] == package_payload["evidence"]
        assert snapshot["deterministicFindings"] == package_payload["deterministicFindings"]
        return super().analyze(package)


def request_at(hour: int) -> AnalysisRequest:
    return AnalysisRequest(
        target="orders-api",
        start_time=datetime(2026, 9, 20, hour, tzinfo=UTC),
        end_time=datetime(2026, 9, 20, hour, 10, tzinfo=UTC),
    )


def test_both_scenarios_use_same_pipeline_and_persist_all_stages() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    repository = AnalysisRepository(engine)
    provider = SnapshotCheckingProvider(repository)
    pipeline = AnalysisPipeline(MockAdapter(), provider, repository)

    query_report = pipeline.run(request_at(10), "query-regression")
    connection_report = pipeline.run(request_at(11), "connection-pressure")

    assert query_report.sections[0].title == "Query Efficiency Regression"
    assert connection_report.sections[0].title == "Connection Pressure"
    assert query_report.analysis_id != connection_report.analysis_id
    assert repository.get_result(query_report.analysis_id) is not None
    assert repository.get_result(connection_report.analysis_id) is not None
    assert repository.get_package(query_report.analysis_id) is not None
    assert repository.get_package(connection_report.analysis_id) is not None
    for model in [AnalysisRun, EvidenceSnapshot, DeterministicResult, AIAttempt, AnalysisResult]:
        assert repository.count_records(model) == 2


def test_insufficient_evidence_is_persisted_without_ai_call() -> None:
    class UnavailableAdapter:
        def collect(self, request, fixture_name=None):
            return CollectedEvidence(
                evidence=[],
                missing_evidence=["Prometheus unavailable", "Loki unavailable"],
            )

    class ProviderMustNotRun:
        name = "must-not-run"

        def analyze(self, package):
            raise AssertionError("AI must not be called without deterministic findings")

    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    repository = AnalysisRepository(engine)
    pipeline = AnalysisPipeline(UnavailableAdapter(), ProviderMustNotRun(), repository)

    report = pipeline.run(request_at(10))
    snapshot = repository.get_package(report.analysis_id)
    run = repository.get_run(report.analysis_id)

    assert report.status == "insufficient_data"
    assert "Prometheus unavailable" in report.limitations
    assert repository.get_result(report.analysis_id) is not None
    assert run["status"] == "completed"
    assert snapshot is not None
    assert snapshot["evidence"] == []
    assert snapshot["deterministicFindings"] == []
    assert repository.count_records(AIAttempt) == 0


def test_normal_pipeline_call_does_not_select_a_mock_fixture() -> None:
    class CapturingAdapter:
        fixture_name = "unset"

        def collect(self, request, fixture_name=None):
            self.fixture_name = fixture_name
            return CollectedEvidence(evidence=[], missing_evidence=["No live evidence"])

    adapter = CapturingAdapter()
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    report = AnalysisPipeline(
        adapter,
        MockAIProvider(),
        AnalysisRepository(engine),
    ).run(request_at(10))

    assert adapter.fixture_name is None
    assert report.status == "insufficient_data"


def test_development_live_endpoint_uses_multi_source_adapter_without_changing_default(
    monkeypatch,
) -> None:
    class LiveAdapter:
        def __init__(self, adapters):
            assert len(adapters) == 3

        def collect(self, request, fixture_name=None):
            assert fixture_name is None
            return MockAdapter().collect(request, "query-regression")

    monkeypatch.setattr(analyses, "MultiSourceAdapter", LiveAdapter)
    app = create_app(
        Settings(app_env="development", evidence_mode="mock", database_url="sqlite://")
    )
    payload = request_at(10).model_dump(mode="json", by_alias=True)

    response = TestClient(app).post("/api/v1/dev/live/analyses", json=payload)

    assert response.status_code == 200
    assert response.json()["sections"][0]["title"] == "Query Efficiency Regression"
    assert app.state.settings.evidence_mode == "mock"


def test_pipeline_enforces_configured_maximum_window() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    pipeline = AnalysisPipeline(
        MockAdapter(),
        MockAIProvider(),
        AnalysisRepository(engine),
        max_window_minutes=5,
    )
    with pytest.raises(ValueError, match="configured maximum"):
        pipeline.run(request_at(10), "query-regression")


def test_connection_scenario_cites_stable_plan_as_contradicting_evidence() -> None:
    request = request_at(11)
    package = EvidenceBuilder().build(
        "AN-CONTRADICTION",
        request,
        MockAdapter().collect(request, "connection-pressure"),
    )
    findings = DeterministicAnalyzer().analyze(package.evidence)
    package = package.model_copy(update={"deterministic_findings": findings})
    interpretation = MockAIProvider().analyze(package)
    hypothesis = interpretation.sections[0].hypothesis
    evidence = {item.id: item for item in package.evidence}

    assert {"E5", "E6"}.issubset(hypothesis.contradicting_evidence_ids)
    assert evidence["E5"].value["before"] == evidence["E5"].value["after"] == "IXSCAN"
    assert evidence["E6"].value["after"] - evidence["E6"].value["before"] <= 2


def test_report_numeric_values_come_from_contract_b() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    report = AnalysisPipeline(MockAdapter(), MockAIProvider(), AnalysisRepository(engine)).run(
        request_at(10), "query-regression"
    )

    latency = next(chart for chart in report.sections[0].charts if chart.id == "request-p95-ms")
    assert [point.value for point in latency.series] == [200, 1000]
    assert "1000" in " ".join(fact.text for fact in report.sections[0].facts)
    assert all("1300" not in fact.text for fact in report.sections[0].facts)


def test_connection_report_contains_trusted_values_and_contradiction() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    report = AnalysisPipeline(MockAdapter(), MockAIProvider(), AnalysisRepository(engine)).run(
        request_at(11), "connection-pressure"
    )

    connections = next(
        chart for chart in report.sections[0].charts if chart.id == "connection-utilization-percent"
    )
    assert [point.value for point in connections.series] == [25, 92]
    assert report.sections[0].hypothesis.contradicting_evidence_ids == ["E5", "E6"]


def test_connection_report_exposes_illustrative_verification_and_limits() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    report = AnalysisPipeline(MockAdapter(), MockAIProvider(), AnalysisRepository(engine)).run(
        request_at(11), "connection-pressure"
    )

    verification = report.sections[0].verification
    assert len(verification) == 6
    assert all(item.mode == "illustrative" for item in verification)
    assert verification[0].evidence_ids == ["E1"]
    assert "Real production telemetry" in " ".join(report.limitations)
    assert "Definitive root cause is not established" in " ".join(report.limitations)
    assert "by client/application" in report.sections[0].recommended_checks[0]


def test_connection_report_renders_support_and_contradiction_groups() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    report = AnalysisPipeline(MockAdapter(), MockAIProvider(), AnalysisRepository(engine)).run(
        request_at(11), "connection-pressure"
    )

    facts = report.sections[0].facts
    supporting = {fact.evidence_ids[0] for fact in facts if fact.evidence_ids}
    assert {"E1", "E2", "E3", "E4"}.issubset(supporting)
    assert {"E5", "E6"}.issubset(supporting)


class UnavailableProvider(AIProvider):
    name = "unavailable"

    def analyze(self, package):
        raise RuntimeError("provider unavailable")


def test_provider_failure_returns_deterministic_fallback_report() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    report = AnalysisPipeline(MockAdapter(), UnavailableProvider(), AnalysisRepository(engine)).run(
        request_at(11), "connection-pressure"
    )

    assert report.sections[0].title == "Deterministic findings"
    assert "AI interpretation unavailable" in report.summary
    assert report.sections[0].charts
    assert report.sections[0].verification


def test_query_fallback_report_answers_the_five_engineer_questions() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    report = AnalysisPipeline(MockAdapter(), UnavailableProvider(), AnalysisRepository(engine)).run(
        request_at(10), "query-regression"
    )
    section = report.sections[0]
    html = TEMPLATES.env.get_template("report.html").render(
        report=report.model_dump(mode="json", by_alias=True)
    )

    assert "200" in report.summary and "1000" in report.summary
    assert "documents examined rose" in report.summary
    assert {"request-p95-ms", "documents-examined", "documents-returned", "scan-ratio"} <= {
        chart.id for chart in section.charts
    }
    fact_text = " ".join(fact.text for fact in section.facts)
    assert {"IXSCAN", "COLLSCAN", "400%"} <= set(fact_text.replace(".", " ").split())
    scan_ratio = next(chart for chart in section.charts if chart.id == "scan-ratio")
    assert [point.value for point in scan_ratio.series] == [20, 4000]
    assert section.recommended_checks[0].startswith("Inspect the affected query")
    assert "system.profile" in " ".join(item.query for item in section.verification)
    assert "NOT EXECUTED IN THIS MOCK SCENARIO" in " ".join(html.split())
    assert "What evidence supports this?" in html
    assert all(value in html for value in ["200", "1000", "200000", "50", "IXSCAN", "COLLSCAN"])
    assert "400%" in html and "20.0" in html and "4000.0" in html
    assert "No contradicting evidence was identified." in html
    assert "Not applicable" in html
    assert "Deployment: {" not in html
    assert "Evidence: ;" not in html
