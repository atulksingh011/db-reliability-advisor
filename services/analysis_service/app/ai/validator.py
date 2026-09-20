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

        for section in interpretation.sections:
            for fact in section.facts:
                errors.extend(
                    self._unknown_references(
                        fact.evidence_ids, evidence_ids, f"fact in {section.id}", "evidence"
                    )
                )
                errors.extend(
                    self._unknown_references(
                        fact.deterministic_finding_ids,
                        finding_ids,
                        f"fact in {section.id}",
                        "deterministic finding",
                    )
                )
            hypothesis = section.hypothesis
            errors.extend(
                self._unknown_references(
                    hypothesis.supporting_evidence_ids,
                    evidence_ids,
                    f"hypothesis in {section.id}",
                    "evidence",
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
