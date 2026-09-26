from ..contracts.models import (
    AnalysisPackage,
    Hypothesis,
)
from .base import AIInterpretation, AIInterpretationSection, AIProvider


class MockAIProvider(AIProvider):
    name = "mock"

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
                    hypothesis=Hypothesis(
                        text=(
                            "Hypothesis: the changed query shape may no longer use the existing "
                            "index effectively."
                        ),
                        confidence="medium",
                        supporting_evidence_ids=["E1", "E2", "E3", "E4", "E5"],
                        contradicting_evidence_ids=[],
                    ),
                    recommended_checks=[
                        "Compare the query shape before and after the deployment.",
                        "Run explain('executionStats') against a safe representative query.",
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
                    hypothesis=Hypothesis(
                        text=(
                            "Hypothesis: connection saturation is a better-supported explanation "
                            "than a query/index regression."
                        ),
                        confidence="high",
                        supporting_evidence_ids=["E1", "E2", "E3", "E4"],
                        contradicting_evidence_ids=["E5", "E6"],
                    ),
                    recommended_checks=[
                        "Inspect client pool sizing and checkout wait time.",
                        "Correlate connection failures with the latency window.",
                    ],
                    limitations=[
                        "Mock / illustrative data cannot identify which client exhausted "
                        "connections."
                    ],
                    deterministic_finding_ids=["D1", "D2", "D3"],
                )
            ],
            limitations=[
                "All values are mock / illustrative; replace mock adapters for production evidence."
            ],
        )
