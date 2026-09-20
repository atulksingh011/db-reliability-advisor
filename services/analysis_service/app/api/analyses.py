from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from ..contracts.models import (
    AnalysisAccepted,
    AnalysisRequest,
    AnalysisStatus,
    ValidatedReport,
)
from ..orchestration.pipeline import AnalysisPipeline

router = APIRouter(prefix="/api/v1")
dev_router = APIRouter(prefix="/api/v1/dev/mock")


def _pipeline(request: Request) -> AnalysisPipeline:
    return request.app.state.pipeline


@router.post("/analyses", response_model=AnalysisAccepted, status_code=status.HTTP_201_CREATED)
def create_analysis(payload: AnalysisRequest, request: Request) -> AnalysisAccepted:
    try:
        report = _pipeline(request).run(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AnalysisAccepted(analysis_id=report.analysis_id, status="completed")


@router.get("/analyses/{analysis_id}", response_model=AnalysisStatus)
def get_analysis(analysis_id: str, request: Request) -> AnalysisStatus:
    run = request.app.state.repository.get_run(analysis_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return AnalysisStatus.model_validate(run)


@router.get("/analyses/{analysis_id}/result", response_model=ValidatedReport)
def get_analysis_result(analysis_id: str, request: Request) -> ValidatedReport:
    result = request.app.state.repository.get_result(analysis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Analysis result not found")
    return ValidatedReport.model_validate(result)


def _mock_request(hour: int) -> AnalysisRequest:
    return AnalysisRequest(
        target="orders-api",
        start_time=datetime(2026, 9, 20, hour, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 20, hour, 10, tzinfo=UTC),
    )


@dev_router.post("/query-regression", response_model=ValidatedReport)
def run_query_regression(request: Request) -> ValidatedReport:
    return _pipeline(request).run(_mock_request(10), fixture_name="query-regression")


@dev_router.post("/connection-pressure", response_model=ValidatedReport)
def run_connection_pressure(request: Request) -> ValidatedReport:
    return _pipeline(request).run(_mock_request(11), fixture_name="connection-pressure")


@dev_router.post("/alertmanager", response_model=ValidatedReport)
def receive_mock_alert(request: Request, payload: dict[str, Any]) -> ValidatedReport:
    """Development bridge proving alerts enter through the same Contract A pipeline."""
    del payload  # Controlled foundation hook; DBADV-01 will map real labels and timestamps.
    return _pipeline(request).run(_mock_request(11), fixture_name="connection-pressure")
