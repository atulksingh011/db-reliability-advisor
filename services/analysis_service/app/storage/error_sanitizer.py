"""Safe, bounded diagnostics for durable analysis audit records."""

import re
from dataclasses import dataclass
from typing import Any

_MAX_ERROR_LENGTH = 500
_SECRET_PATTERNS = (
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(\bbearer\s+)[^\s,;]+"), r"\1[REDACTED]"),
    (
        re.compile(
            r"(?i)(\b(?:api[_-]?key|x-api-key|apikey|password|passwd|token|access_token|refresh_token|client_secret|secret)\s*[:=]\s*[\"']?)[^\s,;\"']+"
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(
            r'(?i)(["\'](?:api[_-]?key|x-api-key|apikey|password|passwd|token|access_token|refresh_token|client_secret|secret)["\']\s*:\s*["\'])[^"\']+(["\'])'
        ),
        r"\1[REDACTED]\2",
    ),
    (
        re.compile(
            r"(?i)([?&](?:api[_-]?key|x-api-key|apikey|password|passwd|token|access_token|refresh_token|client_secret|secret)=)[^&#\s]+"
        ),
        r"\1[REDACTED]",
    ),
)


@dataclass(frozen=True)
class SafeAuditError:
    category: str
    message: str


def redact_sensitive_text(value: str) -> str:
    """Redact common credential formats without retaining the secret value."""
    result = value[:_MAX_ERROR_LENGTH]
    for pattern, replacement in _SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def sanitize_error_message(value: str | None, fallback: str = "Audit error") -> str:
    """Keep useful application diagnostics while preventing raw credentials."""
    if not value:
        return fallback
    redacted = redact_sensitive_text(str(value))
    if redacted != str(value)[:_MAX_ERROR_LENGTH]:
        return redacted
    return redacted


def classify_exception(error: BaseException, *, context: str = "analysis") -> SafeAuditError:
    """Return a safe category and message suitable for durable audit storage."""
    text = str(error).lower()
    if "429" in text or "rate limit" in text or "too many requests" in text:
        return SafeAuditError("rate_limit", "AI provider rate limit exceeded.")
    if "401" in text or "403" in text or "unauthorized" in text or "forbidden" in text:
        return SafeAuditError("authentication_error", "AI provider authentication failed.")
    if "503" in text or "service unavailable" in text:
        return SafeAuditError("service_unavailable", "AI provider temporarily unavailable.")
    if isinstance(error, TimeoutError) or "timeout" in text:
        return SafeAuditError("timeout", "AI provider request timed out.")
    if context == "validation":
        return SafeAuditError("validation_error", sanitize_error_message(str(error)))
    if context == "repair":
        return SafeAuditError("repair_failure", "AI provider repair failed.")
    if context == "provider":
        return SafeAuditError("provider_error", "AI provider request failed.")
    return SafeAuditError("analysis_error", sanitize_error_message(str(error), "Analysis failed."))


def sanitize_audit_value(value: Any) -> Any:
    """Defense-in-depth sanitization for JSON values crossing the repository boundary."""
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, list):
        return [sanitize_audit_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_audit_value(item) for key, item in value.items()}
    return value
