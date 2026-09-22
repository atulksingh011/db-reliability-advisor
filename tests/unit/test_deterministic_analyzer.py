from datetime import UTC, datetime

from services.analysis_service.app.adapters.mock import MockAdapter
from services.analysis_service.app.analyzers.deterministic import DeterministicAnalyzer
from services.analysis_service.app.contracts.models import AnalysisRequest


def test_missing_named_evidence_returns_no_partial_rule_findings() -> None:
    findings = DeterministicAnalyzer().analyze([])

    assert findings == []


def test_zero_baselines_do_not_crash_or_divide_by_zero() -> None:
    request = AnalysisRequest(
        target="orders-api",
        start_time=datetime(2026, 9, 20, 10, tzinfo=UTC),
        end_time=datetime(2026, 9, 20, 10, 10, tzinfo=UTC),
    )
    evidence = MockAdapter().collect(request, "query-regression").evidence
    adjusted = [
        item.model_copy(update={"value": {"before": 0, "after": 50}})
        if item.name == "documents_returned"
        else item
        for item in evidence
    ]

    findings = DeterministicAnalyzer().analyze(adjusted)

    assert findings[0].result["percentIncrease"] == 400
    assert all(finding.rule != "scan_ratio_change" for finding in findings)
