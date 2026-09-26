from datetime import UTC, datetime

import pytest

from services.analysis_service.app.adapters.mock import MockAdapter
from services.analysis_service.app.ai.mock_provider import MockAIProvider
from services.analysis_service.app.analyzers.deterministic import DeterministicAnalyzer
from services.analysis_service.app.contracts.models import AnalysisRequest
from services.analysis_service.app.evidence.builder import EvidenceBuilder
from services.analysis_service.app.orchestration.pipeline import AnalysisPipeline
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
    pipeline = AnalysisPipeline(MockAdapter(), MockAIProvider(), repository)

    query_report = pipeline.run(request_at(10), "query-regression")
    connection_report = pipeline.run(request_at(11), "connection-pressure")

    assert query_report.sections[0].title == "Query Efficiency Regression"
    assert connection_report.sections[0].title == "Connection Pressure"
    assert query_report.analysis_id != connection_report.analysis_id
    assert repository.get_result(query_report.analysis_id) is not None
    assert repository.get_result(connection_report.analysis_id) is not None
    for model in [AnalysisRun, EvidenceSnapshot, DeterministicResult, AIAttempt, AnalysisResult]:
        assert repository.count_records(model) == 2


def test_pipeline_enforces_configured_maximum_window() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    pipeline = AnalysisPipeline(
        MockAdapter(), MockAIProvider(), AnalysisRepository(engine), max_window_minutes=5
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
    report = AnalysisPipeline(
        MockAdapter(), MockAIProvider(), AnalysisRepository(engine)
    ).run(request_at(10), "query-regression")

    latency = next(chart for chart in report.sections[0].charts if chart.id == "request-p95-ms")
    assert [point.value for point in latency.series] == [200, 1000]
    assert "1000" in " ".join(fact.text for fact in report.sections[0].facts)
    assert all("1300" not in fact.text for fact in report.sections[0].facts)


def test_connection_report_contains_trusted_values_and_contradiction() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    report = AnalysisPipeline(
        MockAdapter(), MockAIProvider(), AnalysisRepository(engine)
    ).run(request_at(11), "connection-pressure")

    connections = next(
        chart
        for chart in report.sections[0].charts
        if chart.id == "connection-utilization-percent"
    )
    assert [point.value for point in connections.series] == [25, 92]
    assert report.sections[0].hypothesis.contradicting_evidence_ids == ["E5", "E6"]
