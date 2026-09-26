from datetime import timedelta
from uuid import uuid4

from ..adapters.base import EvidenceAdapter
from ..ai.base import AIInterpretation, AIInterpretationSection, AIProvider
from ..ai.validator import GroundingValidationError, GroundingValidator
from ..analyzers.deterministic import DeterministicAnalyzer
from ..contracts.models import AnalysisPackage, AnalysisRequest, Hypothesis, ValidatedReport
from ..evidence.builder import EvidenceBuilder
from ..reports.assembler import ReportAssembler
from ..reports.data_builder import TrustedReportDataBuilder
from ..storage.error_sanitizer import classify_exception, sanitize_error_message
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
        except Exception as exc:
            self.repository.mark_failed(analysis_id, classify_exception(exc).message)
            raise

    def replay(self, source_analysis_id: str) -> ValidatedReport:
        """Run AI/validation/reporting against one immutable stored Contract B snapshot."""
        payload = self.repository.get_package(source_analysis_id)
        source = self.repository.get_run(source_analysis_id)
        if payload is None or source is None:
            raise KeyError(source_analysis_id)
        source_package = AnalysisPackage.model_validate(payload)
        analysis_id = f"AN-{uuid4().hex[:12].upper()}"
        request = AnalysisRequest(
            target=source_package.target,
            start_time=source_package.window.start_time,
            end_time=source_package.window.end_time,
        )
        self.repository.create_run(
            analysis_id,
            request,
            source.get("fixtureName") or "replay",
            replayed_from=source_analysis_id,
        )
        try:
            # Keep the exact historical Contract B in the replay audit. The execution
            # copy receives the new ID so the resulting Contract C belongs to the replay.
            self.repository.save_analysis_package(analysis_id, payload)
            package = source_package.model_copy(update={"analysis_id": analysis_id})
            validated = self._interpret(package, analysis_id)
            trusted = self.trusted_data_builder.build(package)
            report = self.assembler.assemble(package, trusted, validated)
            self.repository.save_result(analysis_id, report.model_dump(mode="json", by_alias=True))
            return report
        except Exception as exc:
            self.repository.mark_failed(analysis_id, classify_exception(exc).message)
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
                attempt_id = self.repository.save_ai_attempt(
                    analysis_id,
                    self.provider.name,
                    interpretation.model_dump(mode="json", by_alias=True),
                    "rejected",
                    [sanitize_error_message(error) for error in exc.errors],
                    model=getattr(self.provider, "model", None),
                    error_category="validation_error",
                )
                safe_errors = [sanitize_error_message(error) for error in exc.errors]
                self.repository.save_validation(
                    analysis_id, attempt_id, 1, False, safe_errors, True
                )
                try:
                    repaired = self.provider.repair(package, safe_errors, raw_response)
                    validated = self.validator.validate(repaired, package)
                    attempt_id = self.repository.save_ai_attempt(
                        analysis_id,
                        self.provider.name,
                        repaired.model_dump(mode="json", by_alias=True),
                        "accepted_after_repair",
                        model=getattr(self.provider, "model", None),
                    )
                    self.repository.save_validation(analysis_id, attempt_id, 2, True)
                except Exception as repair_error:
                    safe_repair_error = classify_exception(repair_error, context="repair")
                    self.repository.save_validation(
                        analysis_id, None, 2, False, [safe_repair_error.message]
                    )
                    return self._fallback(
                        package, analysis_id, [*safe_errors, safe_repair_error.message]
                    )
            else:
                attempt_id = self.repository.save_ai_attempt(
                    analysis_id,
                    self.provider.name,
                    interpretation.model_dump(mode="json", by_alias=True),
                    "accepted",
                    model=getattr(self.provider, "model", None),
                )
                self.repository.save_validation(analysis_id, attempt_id, 1, True)
            return validated
        except Exception as exc:
            safe_error = classify_exception(exc, context="provider")
            if interpretation is not None:
                payload = interpretation.model_dump(mode="json", by_alias=True)
            else:
                payload = {"error": safe_error.message}
            attempt_id = self.repository.save_ai_attempt(
                analysis_id,
                self.provider.name,
                payload,
                "failed",
                [safe_error.message],
                model=getattr(self.provider, "model", None),
                error_category=safe_error.category,
            )
            self.repository.save_validation(
                analysis_id, attempt_id, 1, False, [safe_error.message], True
            )
            try:
                repaired = self.provider.repair(package, [safe_error.message], raw_response)
                validated = self.validator.validate(repaired, package)
                attempt_id = self.repository.save_ai_attempt(
                    analysis_id,
                    self.provider.name,
                    repaired.model_dump(mode="json", by_alias=True),
                    "accepted_after_repair",
                    model=getattr(self.provider, "model", None),
                )
                self.repository.save_validation(analysis_id, attempt_id, 2, True)
                return validated
            except Exception as repair_error:
                safe_repair_error = classify_exception(repair_error, context="repair")
                self.repository.save_validation(
                    analysis_id, None, 2, False, [safe_repair_error.message]
                )
                return self._fallback(
                    package, analysis_id, [safe_error.message, safe_repair_error.message]
                )

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
            model=getattr(self.provider, "model", None),
            error_category="fallback",
        )
        self.repository.save_fallback(
            analysis_id, errors, fallback.model_dump(mode="json", by_alias=True)
        )
        return fallback
