import json

from fastapi.testclient import TestClient

from services.analysis_service.app.ai.base import AIProvider
from services.analysis_service.app.config import Settings


class SecretProvider(AIProvider):
    name = "secret-provider"

    def analyze(self, package):
        raise RuntimeError(
            "Authorization: Bearer TEST_SECRET_SENTINEL api_key=TEST_API_KEY_SECRET "
            "password=TEST_PASSWORD token=TEST_TOKEN"
        )


def test_audit_api_never_exposes_provider_secret(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'audit.db'}")
    from services.analysis_service.app.main import create_app

    app = create_app(
        Settings(
            app_env="test",
            ai_provider="mock",
            database_url=f"sqlite:///{tmp_path / 'audit.db'}",
        )
    )
    app.state.pipeline.provider = SecretProvider()
    client = TestClient(app)

    response = client.post(
        "/api/v1/analyses",
        json={
            "target": "orders-api",
            "startTime": "2026-09-20T10:00:00Z",
            "endTime": "2026-09-20T10:10:00Z",
        },
    )
    assert response.status_code == 201
    analysis_id = response.json()["analysisId"]

    audit_response = client.get(f"/api/v1/analyses/{analysis_id}/audit")
    assert audit_response.status_code == 200
    serialized = json.dumps(audit_response.json(), sort_keys=True)
    assert "TEST_SECRET_SENTINEL" not in serialized
    assert "TEST_API_KEY_SECRET" not in serialized
    assert "TEST_PASSWORD" not in serialized
    assert "TEST_TOKEN" not in serialized
    assert "AI provider request failed." in serialized
