"""The health surface is registered at both the root and the API prefix."""

from fastapi import FastAPI

from tests.conftest import route_paths

EXPECTED = (
    "/health/live",
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/api/v1/health/deep",
)


def test_health_routes_registered(app: FastAPI) -> None:
    paths = route_paths(app)
    missing = [path for path in EXPECTED if path not in paths]
    assert not missing, f"missing routes {missing}; registered: {sorted(paths)}"
