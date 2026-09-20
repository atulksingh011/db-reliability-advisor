from copy import deepcopy

import pytest

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
    interpretation.sections[0].facts[0].deterministic_finding_ids.append("D99")
    with pytest.raises(GroundingValidationError, match="Unknown deterministic finding ID D99"):
        GroundingValidator().validate(interpretation, package)
