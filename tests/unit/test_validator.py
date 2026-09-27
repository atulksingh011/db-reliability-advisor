from copy import deepcopy

import pytest

from services.analysis_service.app.ai.base import (
    AIHypothesis,
    AIInterpretation,
    AIInterpretationSection,
    RecommendedCheck,
)
from services.analysis_service.app.ai.mock_provider import MockAIProvider
from services.analysis_service.app.ai.validator import GroundingValidationError, GroundingValidator
from tests.unit.test_mock_provider import load_package


def test_validator_accepts_valid_mock_response() -> None:
    package = load_package("scenario-a-contract-b.example.json")
    interpretation = MockAIProvider().analyze(package)
    assert GroundingValidator().validate(interpretation, package) is interpretation


def test_validator_rejects_unknown_evidence_id() -> None:
    package = load_package("scenario-a-contract-b.example.json")
    interpretation = deepcopy(MockAIProvider().analyze(package))
    interpretation.sections[0].hypothesis.supporting_evidence_ids.append("E99")
    with pytest.raises(GroundingValidationError, match="Unknown evidence ID E99"):
        GroundingValidator().validate(interpretation, package)


def test_validator_rejects_unknown_deterministic_finding_id() -> None:
    package = load_package("scenario-a-contract-b.example.json")
    interpretation = deepcopy(MockAIProvider().analyze(package))
    interpretation.sections[0].deterministic_finding_ids.append("D99")
    with pytest.raises(GroundingValidationError, match="Unknown deterministic finding ID D99"):
        GroundingValidator().validate(interpretation, package)


def test_ai_interpretation_forbids_authoritative_report_fields() -> None:
    package = load_package("scenario-a-contract-b.example.json")
    interpretation = MockAIProvider().analyze(package).model_dump(by_alias=True)
    interpretation["sections"][0]["charts"] = [
        {
            "id": "wrong",
            "title": "Wrong",
            "type": "bar",
            "series": [{"label": "after", "value": 1300}],
        }
    ]
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        type(MockAIProvider().analyze(package)).model_validate(interpretation)


def test_validator_rejects_bad_numeric_claim() -> None:
    package = load_package("scenario-a-contract-b.example.json")
    interpretation = deepcopy(MockAIProvider().analyze(package))
    interpretation.summary = "Latency increased by 700%."
    with pytest.raises(GroundingValidationError, match="numeric claim 700%"):
        GroundingValidator().validate(interpretation, package)


def test_validator_rejects_unsupported_client_causality() -> None:
    package = load_package("scenario-b-contract-b.example.json")
    interpretation = deepcopy(MockAIProvider().analyze(package))
    interpretation.sections[0].hypothesis.text = "Client checkout-api caused the incident."
    with pytest.raises(GroundingValidationError, match="checkout-api"):
        GroundingValidator().validate(interpretation, package)


def test_validator_rejects_unqualified_missing_index_claim() -> None:
    package = load_package("scenario-a-contract-b.example.json")
    interpretation = deepcopy(MockAIProvider().analyze(package))
    interpretation.sections[0].hypothesis.text = "A missing index definitely caused the problem."
    with pytest.raises(GroundingValidationError, match="missing index"):
        GroundingValidator().validate(interpretation, package)


def test_validator_accepts_qualified_supported_connection_claim() -> None:
    package = load_package("scenario-b-contract-b.example.json")
    interpretation = deepcopy(MockAIProvider().analyze(package))
    interpretation.sections[0].hypothesis.text = (
        "Connection pressure is the best-supported explanation, while query efficiency "
        "remained stable."
    )
    assert GroundingValidator().validate(interpretation, package) is interpretation


@pytest.mark.parametrize(
    ("fixture", "field", "value"),
    [
        ("scenario-a-contract-b.example.json", "summary", "Latency increased by 200%"),
        ("scenario-a-contract-b.example.json", "check", "Create a new index on customerId."),
        ("scenario-a-contract-b.example.json", "check", "Resize the cluster."),
        ("scenario-a-contract-b.example.json", "check", "Change the MongoDB configuration."),
        (
            "scenario-a-contract-b.example.json",
            "hypothesis",
            "Network saturation is the best-supported explanation.",
        ),
        ("scenario-a-contract-b.example.json", "hypothesis", "The deployment broke the index."),
        (
            "scenario-a-contract.example.json" if False else "scenario-a-contract-b.example.json",
            "hypothesis",
            "This is not merely correlated; the deployment broke the index.",
        ),
    ],
)
def test_validator_rejects_reviewed_adversarial_claims(
    fixture: str, field: str, value: str
) -> None:
    package = load_package(fixture)
    interpretation = deepcopy(MockAIProvider().analyze(package))
    if field == "summary":
        interpretation.summary = value
    elif field == "check":
        interpretation.sections[0].recommended_checks[0].description = value
    else:
        interpretation.sections[0].hypothesis.text = value
    with pytest.raises(GroundingValidationError):
        GroundingValidator().validate(interpretation, package)


def test_validator_requires_relevant_deterministic_finding() -> None:
    package = load_package("scenario-a-contract-b.example.json")
    interpretation = deepcopy(MockAIProvider().analyze(package))
    interpretation.sections[0].deterministic_finding_ids = []
    with pytest.raises(GroundingValidationError):
        GroundingValidator().validate(interpretation, package)


def test_validator_accepts_insufficient_data_without_citations() -> None:
    package = load_package("scenario-a-contract-b.example.json").model_copy(
        update={
            "evidence": [],
            "deterministic_findings": [],
            "missing_evidence": ["No meaningful evidence"],
        }
    )
    interpretation = AIInterpretation(
        status="insufficient_data",
        summary="There is not enough evidence to support a hypothesis.",
        sections=[
            AIInterpretationSection(
                id="insufficient",
                category="unknown",
                title="Insufficient evidence",
                hypothesis=AIHypothesis(
                    text="No supported explanation is available.",
                    confidence="low",
                    mode="insufficient_evidence",
                    supporting_evidence_ids=[],
                    contradicting_evidence_ids=[],
                ),
                recommended_checks=[],
                limitations=["No meaningful evidence was collected."],
            )
        ],
        limitations=["No meaningful evidence was collected."],
    )
    assert GroundingValidator().validate(interpretation, package) is interpretation


def test_validator_rejects_unknown_evidence_on_structured_check() -> None:
    package = load_package("scenario-a-contract-b.example.json")
    interpretation = deepcopy(MockAIProvider().analyze(package))
    interpretation.sections[0].recommended_checks[0] = RecommendedCheck(
        type="inspect",
        description="Inspect the query plan.",
        purpose="Verify the plan.",
        evidence_ids=["E999"],
    )
    with pytest.raises(GroundingValidationError):
        GroundingValidator().validate(interpretation, package)
