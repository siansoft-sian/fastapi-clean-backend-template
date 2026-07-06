"""Envelope helpers: shape, meta, and credential redaction."""

from app.core.errors.error_envelope import REDACTED, redact_sensitive
from app.core.responses import api_error, api_success


def test_api_success_shape() -> None:
    body = api_success({"id": 7})
    assert set(body) == {"success", "data", "error", "meta"}
    assert body["success"] is True
    assert body["data"] == {"id": 7}
    assert body["error"] is None
    assert "request_id" in body["meta"]


def test_api_success_merges_extra_meta() -> None:
    body = api_success([1, 2], meta={"pagination": {"total": 2}})
    assert body["meta"]["pagination"] == {"total": 2}
    assert "request_id" in body["meta"]


def test_api_error_shape() -> None:
    body = api_error("CONFLICT", "already exists")
    assert set(body) == {"success", "data", "error", "meta"}
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"] == {"code": "CONFLICT", "message": "already exists", "details": {}}
    assert "request_id" in body["meta"]


def test_api_error_redacts_credential_keys() -> None:
    body = api_error(
        "CONFLICT",
        "boom",
        details={
            "access_token": "leak",
            "Password": "leak",
            "client_secret": "leak",
            "authorization": "Bearer leak",
            "safe_field": "keep-me",
            "nested": {"api_token": "leak", "items": [{"db_password": "leak"}]},
        },
    )
    details = body["error"]["details"]
    assert details["access_token"] == REDACTED
    assert details["Password"] == REDACTED
    assert details["client_secret"] == REDACTED
    assert details["authorization"] == REDACTED
    assert details["safe_field"] == "keep-me"
    assert details["nested"]["api_token"] == REDACTED
    assert details["nested"]["items"][0]["db_password"] == REDACTED


def test_redact_sensitive_does_not_mutate_input() -> None:
    original = {"token": "leak", "nested": {"secret": "leak"}}
    redact_sensitive(original)
    assert original == {"token": "leak", "nested": {"secret": "leak"}}
