from dataclasses import dataclass
from typing import Protocol

from ..contracts.models import AnalysisRequest, Evidence


@dataclass(frozen=True)
class CollectedEvidence:
    evidence: list[Evidence]
    missing_evidence: list[str]


class EvidenceAdapter(Protocol):
    def collect(
        self, request: AnalysisRequest, fixture_name: str | None = None
    ) -> CollectedEvidence:
        """Collect and normalize evidence for the requested analysis window."""
