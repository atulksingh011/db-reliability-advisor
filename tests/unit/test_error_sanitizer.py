import pytest

from services.analysis_service.app.storage.error_sanitizer import redact_sensitive_text


@pytest.mark.parametrize(
    "message",
    [
        "Authorization: Bearer ABC123",
        "api_key=ABC123",
        "api-key: ABC123",
        "x-api-key: ABC123",
        "token=ABC123",
        "password=ABC123",
        '"token": "ABC123"',
        "https://example.test/?api_key=ABC123",
    ],
)
def test_common_secret_formats_are_redacted(message: str) -> None:
    redacted = redact_sensitive_text(message)

    assert "ABC123" not in redacted
    assert "[REDACTED]" in redacted
