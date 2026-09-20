from ..contracts.models import (
    AnalysisPackage,
    ChartPoint,
    Hypothesis,
    ReportChart,
    ReportFact,
    ReportSection,
    VerificationQuery,
)
from .base import AIInterpretation, AIProvider


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
                ReportSection(
                    id="query-efficiency-regression",
                    category="database_query",
                    title="Query Efficiency Regression",
                    facts=[
                        ReportFact(
                            text="Request p95 increased from 200 ms to 1000 ms (400%).",
                            evidence_ids=["E2"],
                            deterministic_finding_ids=["D1"],
                        ),
                        ReportFact(
                            text="The scan ratio increased from 20:1 to 4000:1.",
                            evidence_ids=["E3", "E4"],
                            deterministic_finding_ids=["D2"],
                        ),
                        ReportFact(
                            text="The observed plan changed from IXSCAN to COLLSCAN.",
                            evidence_ids=["E5"],
                            deterministic_finding_ids=["D3"],
                        ),
                    ],
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
                    verification=[
                        VerificationQuery(
                            system="prometheus",
                            label="Request p95",
                            query=(
                                "histogram_quantile(0.95, sum by (le) "
                                "(rate(http_request_duration_seconds_bucket"
                                '{service="orders-api"}[5m])))'
                            ),
                        ),
                        VerificationQuery(
                            system="loki",
                            label="Plan summaries",
                            query='{service="mongodb"} |= "planSummary"',
                        ),
                    ],
                    charts=[
                        ReportChart(
                            id="latency",
                            title="Mock request p95",
                            type="bar",
                            unit="ms",
                            series=[
                                ChartPoint(label="before", value=200),
                                ChartPoint(label="after", value=1000),
                            ],
                        )
                    ],
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
                ReportSection(
                    id="connection-pressure",
                    category="database_connections",
                    title="Connection Pressure",
                    facts=[
                        ReportFact(
                            text=(
                                "Connection utilization increased from 25% to 92% and mock "
                                "connection failures were present."
                            ),
                            evidence_ids=["E1", "E4"],
                            deterministic_finding_ids=["D1"],
                        ),
                        ReportFact(
                            text="Request p95 increased from 220 ms to 1100 ms (400%).",
                            evidence_ids=["E2"],
                            deterministic_finding_ids=["D2"],
                        ),
                        ReportFact(
                            text=(
                                "The query plan remained IXSCAN and scan efficiency stayed "
                                "approximately stable."
                            ),
                            evidence_ids=["E5", "E6"],
                            deterministic_finding_ids=["D3"],
                        ),
                    ],
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
                    verification=[
                        VerificationQuery(
                            system="prometheus",
                            label="MongoDB connections",
                            query=(
                                'mongodb_ss_connections{conn_type="current"} / '
                                'mongodb_ss_connections{conn_type="available"}'
                            ),
                        ),
                        VerificationQuery(
                            system="loki",
                            label="Connection failures",
                            query=('{service="mongodb"} |~ "connection.*(failed|refused|timeout)"'),
                        ),
                    ],
                    charts=[
                        ReportChart(
                            id="connections",
                            title="Mock connection utilization",
                            type="bar",
                            unit="percent",
                            series=[
                                ChartPoint(label="before", value=25),
                                ChartPoint(label="after", value=92),
                            ],
                        )
                    ],
                )
            ],
            limitations=[
                "All values are mock / illustrative; replace mock adapters for production evidence."
            ],
        )
