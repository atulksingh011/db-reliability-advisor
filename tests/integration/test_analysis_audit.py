from datetime import UTC, datetime

import pytest

from services.analysis_service.app.adapters.mock import MockAdapter
from services.analysis_service.app.ai.base import AIProvider
from services.analysis_service.app.ai.mock_provider import MockAIProvider
from services.analysis_service.app.contracts.models import AnalysisRequest
from services.analysis_service.app.orchestration.pipeline import AnalysisPipeline
from services.analysis_service.app.storage.database import (
    create_database_engine,
    initialize_database,
)
from services.analysis_service.app.storage.models import FallbackOutcome, ValidationOutcome
from services.analysis_service.app.storage.repository import AnalysisRepository


def request() -> AnalysisRequest:
    return AnalysisRequest(
        target="orders-api",
        start_time=datetime(2026, 9, 20, 10, tzinfo=UTC),
        end_time=datetime(2026, 9, 20, 10, 10, tzinfo=UTC),
    )


def test_audit_and_replay_use_immutable_contract_b_without_adapter() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    repository = AnalysisRepository(engine)
    adapter = MockAdapter()
    pipeline = AnalysisPipeline(adapter, MockAIProvider(), repository)

    original = pipeline.run(request(), "query-regression")
    original_audit = repository.get_audit(original.analysis_id)
    replay = pipeline.replay(original.analysis_id)
    replay_audit = repository.get_audit(replay.analysis_id)

    assert replay.analysis_id != original.analysis_id
    assert replay_audit["run"]["replayedFrom"] == original.analysis_id
    assert replay_audit["evidence"] == original_audit["evidence"]
    assert replay_audit["deterministicFindings"] == original_audit["deterministicFindings"]
    assert repository.get_audit(original.analysis_id)["evidence"] == original_audit["evidence"]


class FailingAdapter:
    def collect(self, request, fixture_name=None):
        raise RuntimeError("telemetry unavailable")


class UnavailableProvider(AIProvider):
    name = "unavailable"

    def analyze(self, package):
        raise RuntimeError("provider unavailable")


def test_failed_analysis_remains_queryable() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    repository = AnalysisRepository(engine)

    with pytest.raises(RuntimeError, match="telemetry unavailable"):
        AnalysisPipeline(FailingAdapter(), MockAIProvider(), repository).run(request())

    run = repository.list_runs()[0]
    audit = repository.get_audit(run["analysisId"])
    assert run["status"] == "failed"
    assert audit["finalReport"] is None
    assert audit["lifecycle"][-1]["status"] == "failed"


def test_provider_fallback_records_attempt_validation_and_outcome() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    repository = AnalysisRepository(engine)
    report = AnalysisPipeline(MockAdapter(), UnavailableProvider(), repository).run(
        request(), "connection-pressure"
    )

    audit = repository.get_audit(report.analysis_id)
    assert audit["run"]["status"] == "completed_with_fallback"
    assert audit["aiAttempts"][-1]["validationStatus"] == "fallback"
    assert audit["validation"][0]["passed"] is False
    assert repository.count_records(ValidationOutcome) == 2
    assert repository.count_records(FallbackOutcome) == 1
