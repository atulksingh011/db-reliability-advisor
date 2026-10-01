from ..contracts.models import AnalysisPackage
from .base import (
    AIHypothesis,
    AIInterpretation,
    AIInterpretationSection,
    AIProvider,
    RecommendedCheck,
)


class MockAIProvider(AIProvider):
    name = "mock"
    model = "mock-v1"

    def analyze(self, package: AnalysisPackage) -> AIInterpretation:
        rules = {finding.rule for finding in package.deterministic_findings}
        if "connection_pressure" in rules:
            return self._connection_response(package)
        return self._query_response(package)

    @staticmethod
    def _finding_ids(package: AnalysisPackage) -> list[str]:
        return [finding.id for finding in package.deterministic_findings]

    @staticmethod
    def _evidence_ids(package: AnalysisPackage) -> list[str]:
        return list(
            dict.fromkeys(
                evidence_id
                for finding in package.deterministic_findings
                for evidence_id in finding.evidence_ids
            )
        )

    @classmethod
    def _query_response(cls, package: AnalysisPackage) -> AIInterpretation:
        findings = cls._finding_ids(package)
        evidence = cls._evidence_ids(package)
        window_only = all(
            finding.rule == "query_scan_ratio_window" for finding in package.deterministic_findings
        )
        illustrative = all(item.source.system == "mock" for item in package.evidence)
        if window_only:
            summary = (
                "The selected window contains query scan statistics but no regression comparison."
            )
            title = "Query Window Observations"
            hypothesis_text = (
                "Hypothesis: these evidence measurements describe query scan behavior "
                "in one window."
            )
            category = "deterministic_analysis"
            limitations = ["A single observation window cannot establish a regression."]
        else:
            summary = (
                "Mock / illustrative evidence shows a query-efficiency regression."
                if illustrative
                else "Observed query evidence shows changes in scan efficiency and query plan."
            )
            title = "Query Efficiency Regression"
            hypothesis_text = (
                "Hypothesis: the changed query shape may no longer use the existing index "
                "effectively."
            )
            category = "database_query"
            limitations = (
                ["Mock / illustrative data does not prove deployment causation."]
                if illustrative
                else ["The observed comparison does not establish root cause."]
            )
        return AIInterpretation(
            status="warning" if window_only else "critical",
            summary=summary,
            sections=[
                AIInterpretationSection(
                    id="query-efficiency-regression",
                    category=category,
                    title=title,
                    hypothesis=AIHypothesis(
                        text=hypothesis_text,
                        confidence="medium",
                        mode="possible_explanation",
                        supporting_evidence_ids=evidence,
                        contradicting_evidence_ids=[],
                    ),
                    recommended_checks=[
                        RecommendedCheck(
                            type="compare",
                            description=(
                                "Review query-plan and scan-ratio measurements "
                                "from the selected window."
                                if window_only
                                else "Compare the query shape before and after the deployment."
                            ),
                            purpose=(
                                "Determine whether additional comparison evidence is needed."
                                if window_only
                                else "Identify whether the observed query behavior changed."
                            ),
                            evidence_ids=evidence[:2] or evidence,
                        ),
                        RecommendedCheck(
                            type="verify",
                            description=(
                                "Run explain('executionStats') against a safe representative query."
                            ),
                            purpose="Verify the current query plan without changing data.",
                            evidence_ids=evidence[-1:],
                        ),
                    ],
                    limitations=limitations,
                    deterministic_finding_ids=findings,
                )
            ],
            limitations=(
                [
                    "All values are mock / illustrative; replace mock adapters "
                    "for production evidence."
                ]
                if illustrative
                else ["Interpretation is generated by the local mock provider."]
            ),
        )

    @classmethod
    def _connection_response(cls, package: AnalysisPackage) -> AIInterpretation:
        findings = package.deterministic_findings
        finding_ids = [finding.id for finding in findings]
        supporting_evidence = list(
            dict.fromkeys(
                evidence_id
                for finding in findings
                if finding.rule != "query_plan_stable"
                for evidence_id in finding.evidence_ids
            )
        )
        contradicting_evidence = list(
            dict.fromkeys(
                evidence_id
                for finding in findings
                if finding.rule == "query_plan_stable"
                for evidence_id in finding.evidence_ids
            )
        )
        evidence = cls._evidence_ids(package)
        illustrative = all(item.source.system == "mock" for item in package.evidence)
        return AIInterpretation(
            status="critical",
            summary=(
                "Mock / illustrative evidence supports connection pressure more strongly than "
                "a query/index regression."
            ),
            sections=[
                AIInterpretationSection(
                    id="connection-pressure",
                    category="database_connections",
                    title="Connection Pressure",
                    hypothesis=AIHypothesis(
                        text=(
                            "Hypothesis: connection saturation is a better-supported explanation "
                            "than a query/index regression."
                        ),
                        confidence="high",
                        mode="best_supported_explanation",
                        supporting_evidence_ids=supporting_evidence,
                        contradicting_evidence_ids=contradicting_evidence,
                    ),
                    recommended_checks=[
                        RecommendedCheck(
                            type="inspect",
                            description=(
                                "Inspect active connections, pool utilization, and checkout "
                                "wait time "
                                "by client/application."
                            ),
                            purpose=(
                                "Identify whether one workload is consuming a disproportionate "
                                "share of available connections."
                            ),
                            evidence_ids=evidence[:2] or evidence,
                        ),
                        RecommendedCheck(
                            type="compare",
                            description=(
                                "Correlate connection failures with the latency and error windows."
                            ),
                            purpose=(
                                "Determine whether failed checkouts align with the observed impact."
                            ),
                            evidence_ids=evidence,
                        ),
                    ],
                    limitations=[
                        "Mock / illustrative data cannot identify which client exhausted "
                        "connections; definitive root cause is not established."
                    ],
                    deterministic_finding_ids=finding_ids,
                )
            ],
            limitations=(
                [
                    "All values are mock / illustrative; replace mock adapters "
                    "for production evidence."
                ]
                if illustrative
                else ["Interpretation is generated by the local mock provider."]
            ),
        )
