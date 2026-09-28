from services.analysis_service.app.ai.mock_provider import MockAIProvider
from services.analysis_service.app.contracts.models import EvidenceSource
from services.analysis_service.app.reports.assembler import ReportAssembler
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


def test_report_assembler_maps_trusted_data_to_multi_section_references() -> None:
    package = load_package("scenario-a-contract-b.example.json")
    interpretation = MockAIProvider().analyze(package)
    first = interpretation.sections[0].model_copy(
        update={
            "id": "latency",
            "hypothesis": interpretation.sections[0].hypothesis.model_copy(
                update={"supporting_evidence_ids": ["E2"]}
            ),
            "deterministic_finding_ids": ["D1"],
        }
    )
    second = interpretation.sections[0].model_copy(
        update={
            "id": "plan",
            "title": "Query plan",
            "hypothesis": interpretation.sections[0].hypothesis.model_copy(
                update={
                    "text": "Hypothesis: the query plan is relevant to this report.",
                    "supporting_evidence_ids": ["E5"],
                }
            ),
            "deterministic_finding_ids": ["D3"],
        }
    )
    interpretation = interpretation.model_copy(update={"sections": [first, second]})

    report = ReportAssembler().assemble(
        package, TrustedReportDataBuilder().build(package), interpretation
    )

    first_ids = {
        evidence_id for fact in report.sections[0].facts for evidence_id in fact.evidence_ids
    }
    second_ids = {
        evidence_id for fact in report.sections[1].facts for evidence_id in fact.evidence_ids
    }
    assert first_ids == {"E2"}
    assert second_ids == {"E5"}
    assert [chart.id for chart in report.sections[0].charts] == ["request-p95-ms"]
    assert report.sections[1].charts == []
    assert [item.evidence_ids for item in report.sections[0].verification] == [["E2"]]
    assert [item.evidence_ids for item in report.sections[1].verification] == [["E5"]]
