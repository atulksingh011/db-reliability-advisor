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
            return self._connection_response()
        return self._query_response()

    @staticmethod
    def _query_response() -> AIInterpretation:
        return AIInterpretation(
            status="critical",
            summary=(
                "Mock / illustrative evidence shows a query-efficiency regression after "
                "a deployment marker."
            ),
            sections=[
                AIInterpretationSection(
                    id="query-efficiency-regression",
                    category="database_query",
                    title="Query Efficiency Regression",
                    hypothesis=AIHypothesis(
                        text=(
                            "Hypothesis: the changed query shape may no longer use the existing "
                            "index effectively."
                        ),
                        confidence="medium",
                        mode="possible_explanation",
                        supporting_evidence_ids=["E1", "E2", "E3", "E4", "E5"],
                        contradicting_evidence_ids=[],
                    ),
                    recommended_checks=[
                        RecommendedCheck(
                            type="compare",
                            description="Compare the query shape before and after the deployment.",
                            purpose="Identify whether the observed query behavior changed.",
                            evidence_ids=["E1", "E5"],
                        ),
                        RecommendedCheck(
                            type="verify",
                            description=(
                                "Run explain('executionStats') against a safe representative query."
                            ),
                            purpose="Verify the current query plan without changing data.",
                            evidence_ids=["E5"],
                        ),
                    ],
                    limitations=["Mock / illustrative data does not prove deployment causation."],
                    deterministic_finding_ids=["D1", "D2", "D3"],
                )
            ],
            limitations=[
                "All values are mock / illustrative; replace mock adapters for production evidence."
            ],
        )

    @staticmethod
    def _connection_response() -> AIInterpretation:
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
                        supporting_evidence_ids=["E1", "E2", "E3", "E4"],
                        contradicting_evidence_ids=["E5", "E6"],
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
                            evidence_ids=["E1", "E4"],
                        ),
                        RecommendedCheck(
                            type="compare",
                            description=(
                                "Correlate connection failures with the latency and error windows."
                            ),
                            purpose=(
                                "Determine whether failed checkouts align with the observed impact."
                            ),
                            evidence_ids=["E2", "E3", "E4"],
                        ),
                    ],
                    limitations=[
                        "Mock / illustrative data cannot identify which client exhausted "
                        "connections; definitive root cause is not established."
                    ],
                    deterministic_finding_ids=["D1", "D2", "D3"],
                )
            ],
            limitations=[
                "All values are mock / illustrative; replace mock adapters for production evidence."
            ],
        )
