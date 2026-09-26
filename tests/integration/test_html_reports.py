from fastapi.testclient import TestClient

from services.analysis_service.app.config import Settings
from services.analysis_service.app.storage.models import FeedbackRecord


def test_mock_report_renders_and_feedback_form_creates_contract_d(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    from services.analysis_service.app.main import create_app

    app = create_app(Settings(app_env="development", database_url="sqlite://", ai_provider="mock"))
    client = TestClient(app)

    response = client.post("/api/v1/dev/mock/connection-pressure")
    assert response.status_code == 200
    report = response.json()
    report_response = client.get(f"/analyses/{report['analysisId']}/report")
    assert report_response.status_code == 200
    assert "Connection Pressure" in report_response.text
    assert 'name="analysisId"' in report_response.text
    assert 'name="verdict" value="partially_correct"' in report_response.text

    feedback_response = client.post(
        f"/api/v1/analyses/{report['analysisId']}/feedback",
        data={
            "analysisId": report["analysisId"],
            "verdict": "partially_correct",
            "comment": "Useful report",
        },
    )
    assert feedback_response.status_code == 201
    assert "Feedback recorded" in feedback_response.text
    assert app.state.feedback_repository.count_records(FeedbackRecord) == 1


def test_report_template_escapes_ai_controlled_text() -> None:
    from services.analysis_service.app.reporting.renderer import TEMPLATES

    template = TEMPLATES.env.get_template("report.html")
    rendered = template.render(
        report={
            "target": "<script>alert(1)</script>",
            "status": "warning",
            "window": {"startTime": "start", "endTime": "end"},
            "summary": "<script>alert('x')</script>",
            "analysisId": "AN-TEST",
            "sections": [],
            "limitations": [],
        }
    )
    assert "&lt;script&gt;" in rendered
    assert "<script>alert" not in rendered


def test_manual_analysis_form_redirects_to_report(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    from services.analysis_service.app.main import create_app

    app = create_app(Settings(app_env="production", database_url="sqlite://", ai_provider="mock"))
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Manual analysis" in response.text
    submitted = client.post(
        "/analyses/manual",
        data={
            "target": "orders-api",
            "startTime": "2026-09-20T11:00",
            "endTime": "2026-09-20T11:10",
        },
        follow_redirects=False,
    )
    assert submitted.status_code == 303
    assert submitted.headers["location"].startswith("/analyses/AN-")


def test_manual_analysis_form_reports_invalid_window(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    from services.analysis_service.app.main import create_app

    app = create_app(Settings(app_env="production", database_url="sqlite://", ai_provider="mock"))
    response = TestClient(app).post(
        "/analyses/manual",
        data={
            "target": "orders-api",
            "startTime": "2026-09-20T11:10",
            "endTime": "2026-09-20T11:00",
        },
    )
    assert response.status_code == 422
    assert "startTime must be earlier than endTime" in response.text
