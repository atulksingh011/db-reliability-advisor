import httpx

from ..contracts.models import AnalysisRequest
from .base import CollectedEvidence


class LokiAdapter:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def ready(self) -> bool:
        response = httpx.get(f"{self.base_url}/ready", timeout=2)
        return response.is_success

    def collect(
        self, request: AnalysisRequest, fixture_name: str | None = None
    ) -> CollectedEvidence:
        # TODO(DBADV-02): Implement bounded LogQL retrieval and event normalization.
        raise NotImplementedError("Loki evidence collection belongs to DBADV-02")
