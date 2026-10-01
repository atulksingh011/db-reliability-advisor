from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from services.analysis_service.app.contracts.models import AnalysisRequest, Feedback
from services.analysis_service.app.storage.database import (
    create_database_engine,
    initialize_database,
)
from services.analysis_service.app.storage.feedback_repository import FeedbackRepository
from services.analysis_service.app.storage.models import AnalysisRun, FeedbackRecord
from services.analysis_service.app.storage.repository import AnalysisRepository


def test_sqlite_repository_create_load_and_feedback() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    repository = AnalysisRepository(engine)
    request = AnalysisRequest(
        target="orders-api",
        start_time=datetime(2026, 9, 20, 10, tzinfo=UTC),
        end_time=datetime(2026, 9, 20, 10, 10, tzinfo=UTC),
    )
    repository.create_run("AN-TEST", request, "query-regression")

    run = repository.get_run("AN-TEST")
    assert run is not None
    assert run["request"]["target"] == "orders-api"
    assert repository.count_records(AnalysisRun) == 1

    feedback_repository = FeedbackRepository(engine)
    feedback_id = feedback_repository.add_feedback(
        Feedback(analysis_id="AN-TEST", verdict="correct", comment="mock assessment")
    )
    assert feedback_id == 1
    assert feedback_repository.count_records(FeedbackRecord) == 1
    audit = repository.get_audit("AN-TEST")
    assert audit is not None
    stored_feedback = audit["feedback"][0]
    assert {key: value for key, value in stored_feedback.items() if key != "createdAt"} == {
        "id": feedback_id,
        "analysisId": "AN-TEST",
        "findingId": None,
        "verdict": "correct",
        "comment": "mock assessment",
    }
    assert stored_feedback["createdAt"]


def test_feedback_rejects_unknown_analysis_or_finding_and_long_comment() -> None:
    engine = create_database_engine("sqlite://")
    initialize_database(engine)
    repository = AnalysisRepository(engine)
    feedback_repository = FeedbackRepository(engine)
    request = AnalysisRequest(
        target="orders-api",
        start_time=datetime(2026, 9, 20, 10, tzinfo=UTC),
        end_time=datetime(2026, 9, 20, 10, 10, tzinfo=UTC),
    )
    repository.create_run("AN-TEST", request, "query-regression")
    repository.save_analysis_package("AN-TEST", {"deterministicFindings": [{"id": "F-1"}]})

    with pytest.raises(KeyError):
        feedback_repository.add_feedback(Feedback(analysis_id="AN-MISSING", verdict="correct"))
    with pytest.raises(ValueError, match="Finding not found"):
        feedback_repository.add_feedback(
            Feedback(analysis_id="AN-TEST", finding_id="F-2", verdict="incorrect")
        )
    with pytest.raises(ValidationError):
        Feedback(analysis_id="AN-TEST", verdict="correct", comment="x" * 4001)
