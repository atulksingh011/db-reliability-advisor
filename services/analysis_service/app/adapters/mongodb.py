from pymongo import MongoClient

from ..contracts.models import AnalysisRequest
from .base import CollectedEvidence


class MongoMetadataAdapter:
    def __init__(self, uri: str):
        self.uri = uri

    def ping(self) -> bool:
        with MongoClient(self.uri, serverSelectionTimeoutMS=2000) as client:
            return bool(client.admin.command("ping")["ok"])

    def collect(
        self, request: AnalysisRequest, fixture_name: str | None = None
    ) -> CollectedEvidence:
        # TODO(DBADV-02): Collect allow-listed metadata only. Never let AI mutate MongoDB.
        raise NotImplementedError("MongoDB metadata collection belongs to DBADV-02")
