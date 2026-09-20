from typing import Any

from ..contracts.models import DeterministicFinding, Evidence


class DeterministicAnalyzer:
    """Small, explicit rule set sufficient for the two foundation fixtures."""

    def analyze(self, evidence: list[Evidence]) -> list[DeterministicFinding]:
        by_name = {item.name: item for item in evidence}
        if "connection_utilization_percent" in by_name:
            return self._connection_pressure(by_name)
        if "documents_examined" in by_name:
            return self._query_regression(by_name)
        # TODO(DBADV-02): Add rule registration only when real scenario requirements exist.
        return []

    @staticmethod
    def _comparison(evidence: Evidence) -> dict[str, Any]:
        if not isinstance(evidence.value, dict):
            raise ValueError(f"Evidence {evidence.id} must contain a comparison object")
        return evidence.value

    def _latency_finding(self, latency: Evidence, finding_id: str) -> DeterministicFinding:
        value = self._comparison(latency)
        before = float(value["before"])
        after = float(value["after"])
        increase = round(((after - before) / before) * 100)
        return DeterministicFinding(
            id=finding_id,
            rule="latency_percent_change",
            result={"percentIncrease": increase, "beforeMs": before, "afterMs": after},
            evidence_ids=[latency.id],
        )

    def _query_regression(self, items: dict[str, Evidence]) -> list[DeterministicFinding]:
        examined = items["documents_examined"]
        returned = items["documents_returned"]
        plan = items["query_plan"]
        examined_value = self._comparison(examined)
        returned_value = self._comparison(returned)
        plan_value = self._comparison(plan)
        return [
            self._latency_finding(items["request_p95_ms"], "D1"),
            DeterministicFinding(
                id="D2",
                rule="scan_ratio_change",
                result={
                    "before": examined_value["before"] / returned_value["before"],
                    "after": examined_value["after"] / returned_value["after"],
                },
                evidence_ids=[examined.id, returned.id],
            ),
            DeterministicFinding(
                id="D3",
                rule="query_plan_change",
                result={"before": plan_value["before"], "after": plan_value["after"]},
                evidence_ids=[plan.id],
            ),
        ]

    def _connection_pressure(self, items: dict[str, Evidence]) -> list[DeterministicFinding]:
        connections = items["connection_utilization_percent"]
        failures = items["connection_failures"]
        connection_value = self._comparison(connections)
        plan = items["query_plan"]
        plan_value = self._comparison(plan)
        ratio = items["scan_ratio"]
        ratio_value = self._comparison(ratio)
        change_percent = round(
            ((ratio_value["after"] - ratio_value["before"]) / ratio_value["before"]) * 100
        )
        return [
            DeterministicFinding(
                id="D1",
                rule="connection_pressure",
                result={
                    "beforePercent": connection_value["before"],
                    "afterPercent": connection_value["after"],
                    "thresholdPercent": 90,
                },
                evidence_ids=[connections.id, failures.id],
            ),
            self._latency_finding(items["request_p95_ms"], "D2"),
            DeterministicFinding(
                id="D3",
                rule="query_plan_stable",
                result={"plan": plan_value["after"], "scanRatioChangePercent": change_percent},
                evidence_ids=[plan.id, ratio.id],
            ),
        ]
