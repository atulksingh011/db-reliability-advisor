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
    model_config = ConfigDict(extra="forbid")

    claim: str
    classification: Literal[
        "supported", "partially_supported", "unsupported", "contradicted", "overstated"
    ]
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    supporting_finding_ids: list[str] = Field(default_factory=list)
    reason: str


class SemanticGroundingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    claims: list[GroundingClaim]
    errors: list[str] = Field(default_factory=list)
    repair_instructions: list[str] = Field(default_factory=list)


class GroundingValidator:
    """Validate structured AI references before they become Contract C."""

    _numeric_pattern = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?\s*%?")
    _causal_pattern = re.compile(
        r"\b(caus(?:e|ed|es|ing)|because|due to|responsible for|triggered|resulted? from|"
        r"led to|driving|driven by|primary driver|explains|root cause|broke|breaks|breaking)\b",
        re.IGNORECASE,
    )
    _mutation_pattern = re.compile(
        r"\b(create|drop|delete|update|insert|terminate|kill|resize|restart|change|modify|"
        r"increase|decrease|scale|apply|set|alter|provision|reconfigure)\b",
        re.IGNORECASE,
    )
    _category_terms = {
        "database_query": {
            "query",
            "index",
            "plan",
            "scan",
            "execution",
            "latency",
            "document",
            "efficiency",
        },
        "database_connections": {
            "connection",
            "connections",
            "pool",
            "checkout",
            "failure",
            "failures",
            "pressure",
        },
        "deterministic_analysis": {"finding", "measurement", "evidence"},
        "unknown": {"unknown", "insufficient", "evidence"},
    }
    _category_rules = {
        "database_query": {"latency_percent_change", "scan_ratio_change", "query_plan_change"},
        "database_connections": {"connection_pressure", "latency_percent_change"},
        "deterministic_analysis": set(),
        "unknown": set(),
    }

    def validate(
        self, interpretation: AIInterpretation, package: AnalysisPackage
    ) -> AIInterpretation:
        evidence_ids = {item.id for item in package.evidence}
        finding_ids = {item.id for item in package.deterministic_findings}
        errors: list[str] = []
        insufficient = interpretation.status == "insufficient_data"

        if not interpretation.sections and not insufficient:
            errors.append("Interpretation must contain at least one section")

        for section in interpretation.sections:
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

            if insufficient:
                if hypothesis.mode != "insufficient_evidence":
                    errors.append(
                        f"Insufficient-data hypothesis in {section.id} must use "
                        "insufficient_evidence mode"
                    )
                if hypothesis.supporting_evidence_ids or hypothesis.contradicting_evidence_ids:
                    errors.append(
                        f"Insufficient-data hypothesis in {section.id} cannot cite evidence"
                    )
                if section.deterministic_finding_ids or section.recommended_checks:
                    errors.append(
                        f"Insufficient-data section {section.id} cannot claim findings or actions"
                    )
                continue

            if hypothesis.mode == "insufficient_evidence":
                errors.append(
                    f"Substantive hypothesis in {section.id} cannot use insufficient_evidence mode"
                )
            if not hypothesis.supporting_evidence_ids:
                errors.append(f"Hypothesis in {section.id} must cite supporting evidence")
            if not section.limitations:
                errors.append(f"Hypothesis in {section.id} must include limitations")
            if not section.recommended_checks and interpretation.status in {"warning", "critical"}:
                errors.append(
                    f"Problem report section {section.id} must include recommended checks"
                )

            allowed_categories = self._allowed_categories(package)
            if section.category not in allowed_categories:
                errors.append(
                    f"Hypothesis category {section.category} in {section.id} is not "
                    "supported by Contract B"
                )
            else:
                errors.extend(self._category_issues(section, package))

            for check in section.recommended_checks:
                errors.extend(
                    self._text_issues(check.description, f"recommended check in {section.id}")
                )
                errors.extend(
                    self._text_issues(check.purpose, f"recommended check purpose in {section.id}")
                )
                errors.extend(
                    self._unknown_references(
                        check.evidence_ids,
                        evidence_ids,
                        f"recommended check in {section.id}",
                        "evidence",
                    )
                )
                if self._mutation_pattern.search(check.description):
                    errors.append(
                        f"Recommended check in {section.id} is not read-only: {check.description}"
                    )
                if not check.evidence_ids:
                    errors.append(f"Recommended check in {section.id} must cite evidence")

            errors.extend(self._text_issues(interpretation.summary, "summary"))
            errors.extend(self._text_issues(hypothesis.text, f"hypothesis in {section.id}"))

        if errors:
            raise GroundingValidationError(errors)

        semantic = self.semantic_audit(interpretation, package)
        if not semantic.valid:
            raise GroundingValidationError(semantic.errors)
        return interpretation

    def _allowed_categories(self, package: AnalysisPackage) -> set[str]:
        rules = {finding.rule for finding in package.deterministic_findings}
        if not rules:
            return {"unknown", "deterministic_analysis"}
        allowed = {
            category
            for category, category_rules in self._category_rules.items()
            if rules & category_rules
        }
        return allowed or {"deterministic_analysis"}

    def _category_issues(self, section, package: AnalysisPackage) -> list[str]:
        errors: list[str] = []
        category = section.category
        hypothesis = section.hypothesis
        text_words = set(re.findall(r"[a-z]+", hypothesis.text.lower()))
        if not text_words.intersection(self._category_terms[category]):
            errors.append(f"Hypothesis in {section.id} does not describe its supported category")

        relevant = [
            finding
            for finding in package.deterministic_findings
            if finding.rule in self._category_rules[category]
        ]
        relevant_ids = {finding.id for finding in relevant}
        if relevant and not relevant_ids.intersection(section.deterministic_finding_ids):
            errors.append(f"Hypothesis in {section.id} must cite a relevant deterministic finding")

        stable = [
            finding
            for finding in package.deterministic_findings
            if finding.rule == "query_plan_stable"
        ]
        if category == "database_connections" and stable:
            required = {evidence_id for finding in stable for evidence_id in finding.evidence_ids}
            if not required.issubset(set(hypothesis.contradicting_evidence_ids)):
                errors.append(f"Hypothesis in {section.id} must acknowledge stable query evidence")
        return errors

    def _text_issues(self, text: str, context: str) -> list[str]:
        issues: list[str] = []
        numeric = self._numeric_pattern.search(text)
        if numeric:
            issues.append(
                f"{context} contains an authoritative numeric claim {numeric.group(0).strip()}"
            )
        causal = self._causal_pattern.search(text)
        if context.startswith("hypothesis") and causal:
            issues.append(f"{context} contains unsupported causal wording: {text}")
        return issues

    def semantic_audit(
        self, interpretation: AIInterpretation, package: AnalysisPackage
    ) -> SemanticGroundingResult:
        claims: list[GroundingClaim] = []
        errors: list[str] = []
        texts = [("summary", interpretation.summary)]
        for section in interpretation.sections:
            texts.append((f"hypothesis in {section.id}", section.hypothesis.text))
            texts.extend(
                (f"recommended check in {section.id}", check.description)
                for check in section.recommended_checks
            )
            texts.extend(
                (f"limitation in {section.id}", limitation) for limitation in section.limitations
            )
        texts.extend(("global limitation", item) for item in interpretation.limitations)
        for context, text in texts:
            issue_list = self._text_issues(text, context)
            claims.append(
                GroundingClaim(
                    claim=text,
                    classification="supported" if not issue_list else "overstated",
                    reason="Claim is structurally consistent with the bounded interpretation model."
                    if not issue_list
                    else " ".join(issue_list),
                )
            )
            errors.extend(issue_list)
        return SemanticGroundingResult(
            valid=not errors,
            claims=claims,
            errors=errors,
            repair_instructions=[
                "Use only supported hypothesis categories and trusted references.",
                "Remove quantitative or causal claims from interpretation prose.",
            ]
            if errors
            else [],
        )

    @staticmethod
    def _unknown_references(
        referenced: list[str], known: set[str], context: str, kind: str
    ) -> list[str]:
        return [
            f"Unknown {kind} ID {item} referenced by {context}"
            for item in referenced
            if item not in known
        ]
