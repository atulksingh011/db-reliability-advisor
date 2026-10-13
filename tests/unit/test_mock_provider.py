import json
from pathlib import Path

import pytest

from services.analysis_service.app.ai.mock_provider import MockAIProvider
from services.analysis_service.app.ai.validator import GroundingValidator
from services.analysis_service.app.contracts.models import AnalysisPackage

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"


def load_package(name: str) -> AnalysisPackage:
    return AnalysisPackage.model_validate(json.loads((EXAMPLES / name).read_text()))


@pytest.mark.parametrize(
    ("fixture", "expected_title", "expected_phrase"),
    [
        (
            "scenario-a-contract-b.example.json",
            "Query Efficiency Regression",
            "query-efficiency regression",
        ),
        (
            "scenario-b-contract-b.example.json",
            "Connection Pressure",
            "connection pressure",
        ),
    ],
)
def test_mock_provider_supports_both_scenarios(
    fixture: str, expected_title: str, expected_phrase: str
) -> None:
    response = MockAIProvider().analyze(load_package(fixture))
    assert response.sections[0].title == expected_title
    assert expected_phrase in response.summary.lower()
    assert response.sections[0].hypothesis.text.startswith("Hypothesis:")
    assert not hasattr(response.sections[0], "facts")
    assert not hasattr(response.sections[0], "charts")
    assert not hasattr(response.sections[0], "verification")


def test_mock_provider_cites_only_findings_present_in_partial_contract_b() -> None:
    package = load_package("scenario-a-contract-b.example.json")
    selected = [
        finding
        for finding in package.deterministic_findings
        if finding.rule in {"scan_ratio_change", "query_plan_change"}
    ]
    findings = [
        finding.model_copy(update={"id": f"D{index}"})
        for index, finding in enumerate(selected, start=1)
    ]
    partial_package = package.model_copy(update={"deterministic_findings": findings})

    interpretation = MockAIProvider().analyze(partial_package)

    assert interpretation.sections[0].deterministic_finding_ids == ["D1", "D2"]
    assert GroundingValidator().validate(interpretation, partial_package) is interpretation
