from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from ..contracts.models import AnalysisRequest
from .base import CollectedEvidence, EvidenceAdapter
from .mock import MockAdapter
from .prometheus import PrometheusAdapter


class MultiSourceAdapter:
    """Collect evidence concurrently while preserving source failures and result order."""

    def __init__(self, adapters: list[EvidenceAdapter]):
        self.adapters = adapters
        self.mock_adapter = MockAdapter()

    def collect(
        self, request: AnalysisRequest, fixture_name: str | None = None
    ) -> CollectedEvidence:
        if fixture_name:
            return self.mock_adapter.collect(request, fixture_name)

        evidence = []
        missing_evidence = []
        prometheus_adapters = [
            adapter for adapter in self.adapters if isinstance(adapter, PrometheusAdapter)
        ]
        context_adapters = [
            adapter for adapter in self.adapters if not isinstance(adapter, PrometheusAdapter)
        ]

        with ThreadPoolExecutor(max_workers=max(len(context_adapters), 1)) as executor:
            futures = [executor.submit(adapter.collect, request) for adapter in context_adapters]
            for adapter, future in zip(context_adapters, futures, strict=True):
                try:
                    collected = future.result()
                except Exception as exc:
                    missing_evidence.append(
                        f"Failed to collect from {type(adapter).__name__}: {exc}"
                    )
                    continue
                evidence.extend(collected.evidence)
                missing_evidence.extend(collected.missing_evidence)

        comparison_time = self._comparison_time(evidence)
        for adapter in prometheus_adapters:
            try:
                collected = adapter.collect(request, comparison_time=comparison_time)
            except Exception as exc:
                missing_evidence.append(
                    f"Failed to collect from {type(adapter).__name__}: {exc}"
                )
                continue
            evidence.extend(collected.evidence)
            missing_evidence.extend(collected.missing_evidence)

        return CollectedEvidence(evidence=evidence, missing_evidence=missing_evidence)

    @staticmethod
    def _comparison_time(evidence) -> datetime | None:
        timestamps = [
            item.timestamp
            for item in evidence
            if item.source.system == "loki"
            and item.name == "context_event"
            and isinstance(item.value, dict)
            and item.value.get("event") in {"deployment", "restart", "scenario_marker"}
            and item.timestamp is not None
        ]
        return min(timestamps) if timestamps else None
