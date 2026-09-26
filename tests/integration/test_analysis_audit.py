import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from services.analysis_service.app.adapters.mock import MockAdapter
from services.analysis_service.app.ai.base import AIInterpretation, AIProvider
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


class SecretProvider(AIProvider):
    name = "secret-provider"

    def analyze(self, package):
        raise RuntimeError(
            "Authorization: Bearer TEST_BEARER_SECRET api_key=TEST_API_KEY_SECRET "
            "password=TEST_PASSWORD token=TEST_TOKEN"
        )


class InvalidThenSecretRepairProvider(AIProvider):
    name = "invalid-provider"

    def analyze(self, package):
        return AIInterpretation(
            status="critical",
            summary="invalid interpretation",
            sections=[],
            limitations=[],
        )

    def repair(self, package, errors, original_response=None):
        raise RuntimeError("x-api-key: TEST_X_API_KEY client_secret=TEST_CLIENT_SECRET")


class InvalidReferenceProvider(AIProvider):
    name = "invalid-reference-provider"

    def analyze(self, package):
        response = MockAIProvider().analyze(package)
        section = response.sections[0].model_copy(
            update={
                "hypothesis": response.sections[0].hypothesis.model_copy(
                    update={"supporting_evidence_ids": ["E999"]}
                )
            }
        )
        return response.model_copy(update={"sections": [section]})


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


def test_secret_bearing_provider_errors_are_not_persisted() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    repository = AnalysisRepository(engine)

    report = AnalysisPipeline(MockAdapter(), SecretProvider(), repository).run(
        request(), "query-regression"
    )
    audit = repository.get_audit(report.analysis_id)
    persisted = json.dumps(audit, sort_keys=True)

    for secret in (
        "TEST_BEARER_SECRET",
        "TEST_API_KEY_SECRET",
        "TEST_PASSWORD",
        "TEST_TOKEN",
    ):
        assert secret not in persisted
    assert audit["aiAttempts"][0]["errorCategory"] == "provider_error"
    assert audit["aiAttempts"][0]["response"] == {"error": "AI provider request failed."}
    assert audit["fallback"]

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT response_payload, validation_errors FROM ai_attempts "
                "UNION ALL SELECT report_payload, reason FROM fallback_outcomes"
            )
        ).all()
    persisted_rows = str(rows)
    for secret in (
        "TEST_BEARER_SECRET",
        "TEST_API_KEY_SECRET",
        "TEST_PASSWORD",
        "TEST_TOKEN",
    ):
        assert secret not in persisted_rows


def test_secret_bearing_repair_errors_are_not_persisted() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    repository = AnalysisRepository(engine)

    report = AnalysisPipeline(MockAdapter(), InvalidThenSecretRepairProvider(), repository).run(
        request(), "query-regression"
    )
    audit = repository.get_audit(report.analysis_id)
    persisted = json.dumps(audit, sort_keys=True)

    assert "TEST_X_API_KEY" not in persisted
    assert "TEST_CLIENT_SECRET" not in persisted
    assert audit["validation"][-1]["errors"] == ["AI provider repair failed."]
    assert audit["fallback"]


def test_safe_validation_error_remains_diagnostic() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    repository = AnalysisRepository(engine)

    report = AnalysisPipeline(MockAdapter(), InvalidReferenceProvider(), repository).run(
        request(), "query-regression"
    )
    audit = repository.get_audit(report.analysis_id)

    assert any("Unknown evidence ID E999" in error for error in audit["validation"][0]["errors"])
