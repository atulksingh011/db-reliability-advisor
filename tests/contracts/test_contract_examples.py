import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from services.analysis_service.app.contracts.models import AnalysisRequest

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"
EXAMPLES = CONTRACTS / "examples"

EXAMPLE_SCHEMAS = {
    "contract-a.example.json": "contract-a-analysis-request.schema.json",
    "scenario-a-contract-b.example.json": "contract-b-analysis-package.schema.json",
    "scenario-b-contract-b.example.json": "contract-b-analysis-package.schema.json",
    "scenario-a-contract-c.example.json": "contract-c-validated-report.schema.json",
    "scenario-b-contract-c.example.json": "contract-c-validated-report.schema.json",
    "contract-d.example.json": "contract-d-feedback.schema.json",
}


@pytest.mark.parametrize(("example_name", "schema_name"), EXAMPLE_SCHEMAS.items())
def test_example_validates_against_schema(example_name: str, schema_name: str) -> None:
    schema = json.loads((CONTRACTS / schema_name).read_text())
    example = json.loads((EXAMPLES / example_name).read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(example)


def test_invalid_contract_a_timestamp_format_fails() -> None:
    schema = json.loads((CONTRACTS / "contract-a-analysis-request.schema.json").read_text())
    invalid = {"target": "orders-api", "startTime": "yesterday", "endTime": "later"}
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(invalid))
    assert len(errors) == 2


def test_contract_a_rejects_reversed_window() -> None:
    with pytest.raises(ValidationError, match="startTime must be earlier"):
        AnalysisRequest.model_validate(
            {
                "target": "orders-api",
                "startTime": "2026-09-20T10:10:00Z",
                "endTime": "2026-09-20T10:00:00Z",
            }
        )


def test_contract_b_supports_optional_provenance_without_mandatory_source_query() -> None:
    schema = json.loads((CONTRACTS / "contract-b-analysis-package.schema.json").read_text())
    example = json.loads((EXAMPLES / "scenario-a-contract-b.example.json").read_text())
    evidence = example["evidence"]

    assert "timestamp" in evidence[0]
    assert "observationWindow" in evidence[1]
    evidence.append(
        {
            "id": "E6",
            "kind": "metadata",
            "name": "collection",
            "value": {},
            "source": {"system": "mongodb"},
        }
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(example)


def test_invalid_feedback_verdict_fails() -> None:
    schema = json.loads((CONTRACTS / "contract-d-feedback.schema.json").read_text())
    invalid = {"analysisId": "AN-123", "verdict": "mostly_right"}
    errors = list(Draft202012Validator(schema).iter_errors(invalid))
    assert errors
