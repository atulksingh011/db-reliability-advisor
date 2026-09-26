import json
from pathlib import Path

import pytest

from services.analysis_service.app.ai.mock_provider import MockAIProvider
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
