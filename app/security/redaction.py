import re
from typing import Any


REDACTED = "[REDACTED]"

SENSITIVE_KEYS = {
    "authorization",
    "proxy_authorization",
    "api_key",
    "apikey",
    "x_api_key",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "client_secret",
    "password",
    "passwd",
    "cookie",
    "set_cookie",
    "secret",
    "credential",
    "credentials",
}

SECRET_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(
        r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|"
        r"client[_-]?secret|password)=([^&\s]+)"
    ),
)


def normalize_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_").replace(" ", "_")


def is_sensitive_key(key: object) -> bool:
    normalized = normalize_key(key)

    return (
        normalized in SENSITIVE_KEYS
        or normalized.endswith("_token")
        or normalized.endswith("_secret")
        or normalized.endswith("_password")
        or normalized.endswith("_credential")
    )


def redact_text(value: str, max_length: int = 2000) -> str:
    """Remove recognizable credentials and bound stored error size."""
    redacted = value

    for pattern in SECRET_PATTERNS:
        if "api[_-]?key" in pattern.pattern:
            redacted = pattern.sub(
                lambda match: f"{match.group(1)}={REDACTED}",
                redacted,
            )
        else:
            redacted = pattern.sub(REDACTED, redacted)

    if len(redacted) > max_length:
        redacted = redacted[:max_length] + "...[TRUNCATED]"

    return redacted


def redact_sensitive(value: Any) -> Any:
    """Recursively sanitize mappings, sequences and strings."""
    if isinstance(value, dict):
        return {
            key: (
                REDACTED
                if is_sensitive_key(key)
                else redact_sensitive(item)
            )
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]

    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)

    if isinstance(value, str):
        return redact_text(value)

    return value