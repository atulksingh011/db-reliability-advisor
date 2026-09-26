from ..contracts.models import AnalysisPackage
from .base import AIInterpretation


class GroundingValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class GroundingValidator:
    """Checks structural citations before AI material can become Contract C."""

    def validate(
        self, interpretation: AIInterpretation, package: AnalysisPackage
    ) -> AIInterpretation:
        evidence_ids = {item.id for item in package.evidence}
        finding_ids = {item.id for item in package.deterministic_findings}
        errors: list[str] = []

        if not interpretation.sections:
            errors.append("Interpretation must contain at least one section")

        for section in interpretation.sections:
            hypothesis = section.hypothesis
            if not hypothesis.supporting_evidence_ids:
                errors.append(f"Hypothesis in {section.id} must cite supporting evidence")
            if not section.recommended_checks and interpretation.status in {"warning", "critical"}:
                errors.append(
                    f"Problem report section {section.id} must include recommended checks"
                )
            if not section.limitations:
                errors.append(f"Hypothesis in {section.id} must include limitations")
            errors.extend(
                self._unknown_references(
                    hypothesis.supporting_evidence_ids,
                    evidence_ids,
                    f"hypothesis in {section.id}",
                    "evidence",
                )
            )

            unsafe_terms = ("drop ", "delete ", "update ", "insert ", "terminate ", "kill ")
            for check in section.recommended_checks:
                if any(term in check.lower() for term in unsafe_terms):
                    errors.append(f"Recommended check in {section.id} is not read-only: {check}")
            errors.extend(
                self._unknown_references(
                    section.supporting_evidence_ids,
                    evidence_ids,
                    f"interpretation in {section.id}",
                    "evidence",
                )
            )
            errors.extend(
                self._unknown_references(
                    section.contradicting_evidence_ids,
                    evidence_ids,
                    f"interpretation in {section.id}",
                    "evidence",
                )
            )
            errors.extend(
                self._unknown_references(
                    section.deterministic_finding_ids,
                    finding_ids,
                    f"interpretation in {section.id}",
                    "deterministic finding",
                )
            )
            errors.extend(
                self._unknown_references(
                    hypothesis.contradicting_evidence_ids,
                    evidence_ids,
                    f"hypothesis in {section.id}",
                    "evidence",
                )
            )

        # TODO(DBADV-03): Add numeric-claim extraction and semantic entailment checks.
        if errors:
            raise GroundingValidationError(errors)
        return interpretation

    @staticmethod
    def _unknown_references(
        referenced: list[str], known: set[str], context: str, kind: str
    ) -> list[str]:
        return [
            f"Unknown {kind} ID {item} referenced by {context}"
            for item in referenced
            if item not in known
        ]
