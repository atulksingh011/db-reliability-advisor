from services.analysis_service.app.contracts.models import EvidenceSource
from services.analysis_service.app.reports.data_builder import TrustedReportDataBuilder
from tests.unit.test_mock_provider import load_package


def test_verification_queries_come_from_evidence_provenance() -> None:
    package = load_package("scenario-a-contract-b.example.json")
    evidence = package.evidence[1].model_copy(
        update={
            "source": EvidenceSource(system="prometheus", query="trusted-query"),
        }
    )
    package = package.model_copy(update={"evidence": [evidence, *package.evidence[2:]]})

    trusted = TrustedReportDataBuilder().build(package)

    verification = trusted.sections["default"].verification
    assert verification[0].query == "trusted-query"
    assert verification[0].system == "prometheus"
    assert verification[0].mode == "actual"
    assert verification[0].evidence_ids == ["E2"]
