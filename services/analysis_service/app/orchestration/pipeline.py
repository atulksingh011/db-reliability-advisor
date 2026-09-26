from datetime import timedelta
from uuid import uuid4

from ..adapters.base import EvidenceAdapter
from ..ai.base import AIInterpretation, AIInterpretationSection, AIProvider
from ..ai.validator import GroundingValidationError, GroundingValidator
from ..analyzers.deterministic import DeterministicAnalyzer
from ..contracts.models import AnalysisRequest, Hypothesis, ValidatedReport
from ..evidence.builder import EvidenceBuilder
from ..reports.assembler import ReportAssembler
from ..reports.data_builder import TrustedReportDataBuilder
from ..storage.repository import AnalysisRepository


class AnalysisPipeline:
    """The one pipeline used by normal requests, both demos, and alert development hooks."""

    def __init__(
        self,
        adapter: EvidenceAdapter,
        provider: AIProvider,
        repository: AnalysisRepository,
        max_window_minutes: int = 60,
    ):
        self.adapter = adapter
        self.provider = provider
        self.repository = repository
        self.max_window = timedelta(minutes=max_window_minutes)
        self.evidence_builder = EvidenceBuilder()
        self.analyzer = DeterministicAnalyzer()
        self.validator = GroundingValidator()
        self.assembler = ReportAssembler()
        self.trusted_data_builder = TrustedReportDataBuilder()

    def run(
        self,
        request: AnalysisRequest,
        fixture_name: str = "query-regression",
    ) -> ValidatedReport:
        if request.end_time - request.start_time > self.max_window:
            maximum_minutes = self.max_window.total_seconds() / 60
            raise ValueError(
                f"Analysis window exceeds configured maximum of {maximum_minutes:g} minutes"
            )

        analysis_id = f"AN-{uuid4().hex[:12].upper()}"
        self.repository.create_run(analysis_id, request, fixture_name)
        try:
            collected = self.adapter.collect(request, fixture_name)
            package = self.evidence_builder.build(analysis_id, request, collected)
            package = package.model_copy(
                update={"deterministic_findings": self.analyzer.analyze(package.evidence)}
            )
            package_payload = package.model_dump(mode="json", by_alias=True)
            self.repository.save_analysis_package(analysis_id, package_payload)

            validated = self._interpret(package, analysis_id)
            trusted = self.trusted_data_builder.build(package)
            report = self.assembler.assemble(package, trusted, validated)
            self.repository.save_result(analysis_id, report.model_dump(mode="json", by_alias=True))
            return report
        except Exception:
            self.repository.mark_failed(analysis_id)
            raise

    def _interpret(self, package, analysis_id: str) -> AIInterpretation:
        interpretation = None
        raw_response = None
        try:
            interpretation = self.provider.analyze(package)
            raw_response = interpretation.model_dump_json(by_alias=True)
            try:
                validated = self.validator.validate(interpretation, package)
            except GroundingValidationError as exc:
                self.repository.save_ai_attempt(
                    analysis_id,
                    self.provider.name,
                    interpretation.model_dump(mode="json", by_alias=True),
                    "rejected",
                    exc.errors,
                )
                try:
                    repaired = self.provider.repair(package, exc.errors, raw_response)
                    validated = self.validator.validate(repaired, package)
                    self.repository.save_ai_attempt(
                        analysis_id,
                        self.provider.name,
                        repaired.model_dump(mode="json", by_alias=True),
                        "accepted_after_repair",
                    )
                except Exception as repair_error:
                    return self._fallback(package, analysis_id, [*exc.errors, str(repair_error)])
            else:
                self.repository.save_ai_attempt(
                    analysis_id,
                    self.provider.name,
                    interpretation.model_dump(mode="json", by_alias=True),
                    "accepted",
                )
            return validated
        except Exception as exc:
            if interpretation is not None:
                payload = interpretation.model_dump(mode="json", by_alias=True)
            else:
                payload = {"error": str(exc)}
            self.repository.save_ai_attempt(
                analysis_id, self.provider.name, payload, "failed", [str(exc)]
            )
            try:
                repaired = self.provider.repair(package, [str(exc)], raw_response)
                validated = self.validator.validate(repaired, package)
                self.repository.save_ai_attempt(
                    analysis_id,
                    self.provider.name,
                    repaired.model_dump(mode="json", by_alias=True),
                    "accepted_after_repair",
                )
                return validated
            except Exception as repair_error:
                return self._fallback(package, analysis_id, [str(exc), str(repair_error)])

    def _fallback(self, package, analysis_id: str, errors: list[str]) -> AIInterpretation:
        fallback = AIInterpretation(
            status="critical" if package.deterministic_findings else "insufficient_data",
            summary=(
                "AI interpretation unavailable; review the deterministic findings and trusted "
                "evidence."
            ),
            sections=[
                AIInterpretationSection(
                    id="deterministic-findings",
                    category="deterministic_analysis",
                    title="Deterministic findings",
                    hypothesis=Hypothesis(
                        text=(
                            "No causal hypothesis was established because AI interpretation was "
                            "unavailable."
                        ),
                        confidence="low",
                        supporting_evidence_ids=[],
                        contradicting_evidence_ids=[],
                    ),
                    recommended_checks=[
                        "Review the cited evidence and trusted verification queries before "
                        "taking action."
                    ],
                    limitations=[
                        "AI interpretation was unavailable; definitive root cause is not "
                        "established."
                    ],
                    deterministic_finding_ids=[item.id for item in package.deterministic_findings],
                )
            ],
            limitations=[
                "AI interpretation unavailable; deterministic findings are shown without a "
                "causal hypothesis."
            ],
        )
        self.repository.save_ai_attempt(
            analysis_id,
            self.provider.name,
            fallback.model_dump(mode="json", by_alias=True),
            "fallback",
            errors,
        )
        return fallback
