from datetime import UTC, datetime

from services.analysis_service.app.contracts.models import AnalysisRequest


def request_for(scenario: str) -> AnalysisRequest:
    hour = 10 if scenario == "query-regression" else 11
    return AnalysisRequest(
        target="orders-api",
        start_time=datetime(2026, 9, 20, hour, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 20, hour, 10, tzinfo=UTC),
    )
