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


def test_feedback_api_enforces_finding_ownership_and_payload_validation(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    from services.analysis_service.app.main import create_app

    app = create_app(Settings(app_env="development", database_url="sqlite://", ai_provider="mock"))
    client = TestClient(app)
    first = client.post("/api/v1/dev/mock/query-regression").json()
    second = client.post("/api/v1/dev/mock/query-regression").json()
    app.state.repository.save_analysis_package(
        second["analysisId"], {"deterministicFindings": [{"id": "D-CROSS"}]}
    )

    valid = client.post(
        f"/api/v1/analyses/{first['analysisId']}/feedback",
        json={
            "analysisId": first["analysisId"],
            "findingId": "D1",
            "verdict": "correct",
            "comment": '<script>alert("feedback-test")</script>',
        },
    )
    assert valid.status_code == 201
    assert client.get(f"/analyses/{first['analysisId']}/report").status_code == 200

    unknown_finding = client.post(
        f"/api/v1/analyses/{first['analysisId']}/feedback",
        json={"analysisId": first["analysisId"], "findingId": "D99", "verdict": "incorrect"},
    )
    assert unknown_finding.status_code == 422
    cross_analysis = client.post(
        f"/api/v1/analyses/{first['analysisId']}/feedback",
        json={
            "analysisId": first["analysisId"],
            "findingId": "D-CROSS",
            "verdict": "incorrect",
        },
    )
    assert cross_analysis.status_code == 422
    assert client.post(
        f"/api/v1/analyses/{second['analysisId']}/feedback",
        json={
            "analysisId": second["analysisId"],
            "findingId": "D-CROSS",
            "verdict": "incorrect",
        },
    ).status_code == 201
    assert client.post(
        f"/api/v1/analyses/{first['analysisId']}/feedback",
        json={"analysisId": first["analysisId"], "verdict": "unsupported"},
    ).status_code == 422
    assert client.post(
        f"/api/v1/analyses/{first['analysisId']}/feedback",
        content="not-json",
        headers={"content-type": "application/json"},
    ).status_code == 422


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


def test_report_template_renders_hypothesis_precision_copy_and_insufficient_state() -> None:
    from services.analysis_service.app.reporting.renderer import TEMPLATES

    section = {
        "id": "test",
        "title": "Test section",
        "category": "database_query",
        "hypothesis": {
            "text": "The query plan is the best-supported explanation.",
            "confidence": "medium",
        },
        "facts": [],
        "recommendedChecks": [],
        "limitations": ["Missing production evidence"],
        "verification": [
            {
                "system": "mock",
                "mode": "illustrative",
                "query": "query <safe>",
                "evidenceIds": ["E1"],
            }
        ],
        "charts": [
            {
                "id": "request-p95-ms",
                "title": "Request p95",
                "unit": "percent",
                "series": [{"label": "Before", "value": 1.5}, {"label": "After", "value": 2.9}],
            }
        ],
    }
    rendered = TEMPLATES.env.get_template("report.html").render(
        report={
            "target": "orders-api",
            "status": "warning",
            "window": {"startTime": "start", "endTime": "end"},
            "summary": "A qualitative query regression is visible.",
            "analysisId": "AN-TEST",
            "sections": [section],
            "limitations": [],
        }
    )
    assert "The query plan is the best-supported explanation." in rendered
    assert "1.5%" in rendered and "2.9%" in rendered
    assert "Copy query" in rendered
    assert "query &lt;safe&gt;" in rendered

    insufficient = TEMPLATES.env.get_template("report.html").render(
        report={
            **{
                "target": "orders-api",
                "status": "insufficient_data",
                "window": {"startTime": "start", "endTime": "end"},
                "summary": "There is not enough evidence.",
                "analysisId": "AN-TEST",
                "limitations": ["Missing production evidence"],
            },
            "sections": [section],
        }
    )
    assert "Evidence status" in insufficient
    assert "Likely issue" not in insufficient
    assert "Hypothesis confidence" not in insufficient


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
