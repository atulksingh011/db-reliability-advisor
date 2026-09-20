from datetime import UTC, datetime

from services.analysis_service.app.contracts.models import AnalysisRequest, Feedback
from services.analysis_service.app.storage.database import (
    create_database_engine,
    initialize_database,
)
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

    feedback_id = repository.add_feedback(
        Feedback(analysis_id="AN-TEST", verdict="correct", comment="mock assessment")
    )
    assert feedback_id == 1
    assert repository.count_records(FeedbackRecord) == 1
