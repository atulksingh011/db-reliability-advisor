import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..contracts.models import AnalysisPackage
from .base import AIInterpretation


class GroundingValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class GroundingClaim(BaseModel):
    """Internal audit output; this is deliberately not a public contract."""

    model_config = ConfigDict(extra="forbid")

    claim: str
    classification: Literal[
        "supported", "partially_supported", "unsupported", "contradicted", "overstated"
    ]
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    supporting_finding_ids: list[str] = Field(default_factory=list)
    reason: str


class SemanticGroundingResult(BaseModel):
    """Deterministic semantic audit result used before Contract C assembly."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    claims: list[GroundingClaim]
    errors: list[str] = Field(default_factory=list)
    repair_instructions: list[str] = Field(default_factory=list)


class GroundingValidator:
    """Checks structural citations and bounded factual grounding before Contract C."""

    _numeric_pattern = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?\s*%?")
    _causal_pattern = re.compile(
        r"\b(caused|because|due to|responsible for|triggered|resulted from|"
        r"led to|leading to|resulting in|driving|driven by|causing|primary driver|"
        r"explains|definitive root cause|"
        r"definitely)\b",
        re.IGNORECASE,
    )
    _uncertainty_terms = (
        "not",
        "may",
        "might",
        "could",
        "possible",
        "likely",
        "hypothesis",
        "consistent",
        "best-supported",
        "cannot",
        "does not",
        "unknown",
        "uncertain",
        "unproven",
    )

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

        if errors:
            raise GroundingValidationError(errors)

        semantic = self.semantic_audit(interpretation, package)
        if not semantic.valid:
            raise GroundingValidationError(semantic.errors)
        return interpretation

    def semantic_audit(
        self, interpretation: AIInterpretation, package: AnalysisPackage
    ) -> SemanticGroundingResult:
        """Audit material wording against trusted values without using outside facts.

        This is intentionally bounded and deterministic. It catches numeric drift,
        unsupported actor/mechanism claims, and unqualified causality. It does not
        attempt to replace human review of nuanced prose.
        """

        trusted_text = self._serialize(package)
        trusted_numbers = self._trusted_numbers(package)
        claims: list[GroundingClaim] = []
        errors: list[str] = []

        texts = [("summary", interpretation.summary)]
        for section in interpretation.sections:
            texts.extend(
                [
                    (f"hypothesis in {section.id}", section.hypothesis.text),
                    *[
                        (f"recommended check in {section.id}", check)
                        for check in section.recommended_checks
                    ],
                    *[
                        (f"limitation in {section.id}", limitation)
                        for limitation in section.limitations
                    ],
                ]
            )
        texts.extend(
            [("global limitation", limitation) for limitation in interpretation.limitations]
        )

        for context, text in texts:
            issue_list = self._claim_issues(
                text,
                trusted_text,
                trusted_numbers,
                semantic_claim=context.startswith(("summary", "hypothesis")),
            )
            classification = "supported" if not issue_list else "overstated"
            claim = GroundingClaim(
                claim=text,
                classification=classification,
                reason="Claim is consistent with trusted Contract B and deterministic findings."
                if not issue_list
                else " ".join(issue_list),
            )
            claims.append(claim)
            errors.extend(f"{context}: {issue}" for issue in issue_list)

        # A claim that explicitly contrasts a hypothesis with stable query behavior
        # must cite that contradiction. A citation elsewhere in the interpretation
        # is not sufficient because Contract C renders sections independently.
        for section in interpretation.sections:
            hypothesis = section.hypothesis.text.lower()
            if (
                re.search(r"\b(stable|unchanged|rather than|instead of)\b", hypothesis)
                and not section.hypothesis.contradicting_evidence_ids
            ):
                error = (
                    f"hypothesis in {section.id}: stable alternative is described without "
                    "contradicting evidence citations"
                )
                errors.append(error)
                for claim in claims:
                    if claim.claim == section.hypothesis.text:
                        claim.classification = "partially_supported"
                        claim.reason = error
                        break

        return SemanticGroundingResult(
            valid=not errors,
            claims=claims,
            errors=errors,
            repair_instructions=(
                [
                    (
                        "Correct unsupported numeric, actor, mechanism, or causal wording "
                        "using only Contract B."
                    ),
                    "Preserve trusted facts and acknowledge material contradictory evidence.",
                ]
                if errors
                else []
            ),
        )

    def _claim_issues(
        self,
        text: str,
        trusted_text: str,
        trusted_numbers: set[str],
        semantic_claim: bool,
    ) -> list[str]:
        issues: list[str] = []
        for match in self._numeric_pattern.findall(text):
            normalized = match.replace(" ", "")
            if normalized.rstrip("%") not in trusted_numbers:
                issues.append(f"numeric claim {normalized} is not present in trusted evidence")

        lowered = text.lower()
        if semantic_claim and self._has_unqualified_causality(text):
            issues.append("causal wording is not qualified by uncertainty")

        # Actor and mechanism names are especially risky because IDs alone do not
        # prove that the cited evidence supports the statement.
        if semantic_claim:
            for actor in re.findall(r"\b[a-z][a-z0-9]+-api\b", lowered):
                if actor not in trusted_text.lower():
                    issues.append(f"actor {actor} is not identified by trusted evidence")
            if "connection leak" in lowered and "leak" not in trusted_text.lower():
                issues.append("connection leak is not established by trusted evidence")
            if "missing index" in lowered and "index" not in trusted_text.lower():
                issues.append("missing index is not established by trusted evidence")
        return issues

    def _has_unqualified_causality(self, text: str) -> bool:
        for sentence in re.split(r"[.!?]", text):
            if self._causal_pattern.search(sentence) and not any(
                term in sentence.lower() for term in self._uncertainty_terms
            ):
                return True
        return False

    @staticmethod
    def _serialize(package: AnalysisPackage) -> str:
        return package.model_dump_json(by_alias=True)

    def _trusted_numbers(self, package: AnalysisPackage) -> set[str]:
        values: set[str] = set()

        def visit(value: object) -> None:
            if isinstance(value, bool):
                return
            if isinstance(value, (int, float)):
                number = (
                    str(value).rstrip("0").rstrip(".")
                    if isinstance(value, float)
                    else str(value)
                )
                values.add(number)
                return
            if isinstance(value, dict):
                for item in value.values():
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        for evidence in package.evidence:
            visit(evidence.value)
        for finding in package.deterministic_findings:
            visit(finding.result)
        return values

    @staticmethod
    def _unknown_references(
        referenced: list[str], known: set[str], context: str, kind: str
    ) -> list[str]:
        return [
            f"Unknown {kind} ID {item} referenced by {context}"
            for item in referenced
            if item not in known
        ]
