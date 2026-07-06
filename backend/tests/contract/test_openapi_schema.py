"""Contract: the OpenAPI schema generates and documents the public surface."""

from fastapi import FastAPI


def test_openapi_schema_generates(app: FastAPI) -> None:
    schema = app.openapi()
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"]
    assert schema["paths"], "schema must document at least one path"


def test_liveness_probes_hidden_but_checks_documented(app: FastAPI) -> None:
    paths = app.openapi()["paths"]
    assert "/health/live" not in paths
    assert "/api/v1/health/live" not in paths
    assert "/api/v1/health/ready" in paths
    assert "/api/v1/health/deep" in paths
