from app.security.redaction import REDACTED, redact_sensitive, redact_text


def test_nested_sensitive_fields_are_redacted():
    payload = {
        "status": "FILLED",
        "headers": {
            "Authorization": "Bearer secret-token",
            "X-API-Key": "very-secret-key",
        },
        "authentication": {
            "access_token": "token-value",
            "refresh-token": "refresh-value",
        },
    }

    result = redact_sensitive(payload)

    assert result["status"] == "FILLED"
    assert result["headers"]["Authorization"] == REDACTED
    assert result["headers"]["X-API-Key"] == REDACTED
    assert result["authentication"]["access_token"] == REDACTED
    assert result["authentication"]["refresh-token"] == REDACTED


def test_recognizable_secret_inside_error_text_is_redacted():
    error = (
        "Request failed with Authorization: Bearer abc.def.secret "
        "and api_key=super-secret-value"
    )

    result = redact_text(error)

    assert "abc.def.secret" not in result
    assert "super-secret-value" not in result
    assert REDACTED in result


def test_non_sensitive_execution_fields_are_preserved():
    payload = {
        "symbol": "SOLUSDT",
        "client_order_id": "sf-approved-order",
        "external_order_id": "123456789",
        "status": "FILLED",
    }

    assert redact_sensitive(payload) == payload


def test_long_error_is_truncated():
    result = redact_text("x" * 3000)

    assert len(result) < 2100
    assert result.endswith("...[TRUNCATED]")