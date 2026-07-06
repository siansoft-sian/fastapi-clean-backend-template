"""Health endpoints.

Liveness is process-only (no dependencies, hidden from the schema, bypasses
auth). Readiness honors the STARTUP_* flags: a dependency that is intentionally
disabled degrades the status (still 200) instead of failing the probe; an
enabled dependency that fails its check returns 503 so orchestrators stop
routing traffic.

The DB ping goes through the opaque pool on `app.state` — this layer never
imports the engine.
"""

from typing import Any, Literal

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.deps import SettingsDep
from app.api.v1.health.schemas import DeepHealthData, LivenessData, ReadinessData
from app.core.config import Settings
from app.core.responses import api_success

logger = structlog.get_logger(__name__)

# Mounted at the app root: the container HEALTHCHECK and orchestrators hit this.
root_router = APIRouter(include_in_schema=False)

# Mounted under settings.api_prefix in create_app().
router = APIRouter(prefix="/health", tags=["health"])


async def _ping_database(pool: Any) -> str:
    """SELECT 1 through the opaque pool. A probe reports, it never raises."""
    if pool is None:
        return "error"
    try:
        await pool.fetchval("SELECT 1")
    except Exception as exc:  # noqa: BLE001 — translated to component state, logged
        logger.warning("readiness_db_ping_failed", error_type=type(exc).__name__)
        return "error"
    return "ok"


async def _ping_redis(redis_client: Any) -> str:
    """PING through the opaque client wrapper. A probe reports, never raises."""
    if redis_client is None:
        return "error"
    try:
        await redis_client.client.ping()
    except Exception as exc:  # noqa: BLE001 — translated to component state, logged
        logger.warning("readiness_redis_ping_failed", error_type=type(exc).__name__)
        return "error"
    return "ok"


async def _readiness(request: Request, settings: Settings) -> ReadinessData:
    components: dict[str, str] = {}
    if settings.startup_connect_database:
        components["database"] = await _ping_database(getattr(request.app.state, "db_pool", None))
    else:
        components["database"] = "disabled"
    if settings.startup_connect_redis:
        components["redis"] = await _ping_redis(getattr(request.app.state, "redis_client", None))
    else:
        components["redis"] = "disabled"
    # Casbin readiness = the enforcer object exists (loaded at startup).
    if settings.startup_load_casbin:
        authz = getattr(request.app.state, "authorization_service", None)
        components["casbin"] = "ok" if authz is not None else "error"
    else:
        components["casbin"] = "disabled"
    # JWKS is "loaded" once the auth milestone ships a verifier; until then a
    # configured URL is unverifiable.
    components["jwks"] = "unknown" if settings.supabase_jwks_url is not None else "disabled"

    states = set(components.values())
    status: Literal["ok", "degraded", "error"]
    if "error" in states:
        status = "error"
    elif "ok" in states and "unknown" not in states:
        status = "ok"
    else:
        status = "degraded"
    return ReadinessData(status=status, components=components)


@root_router.get("/health/live")
async def live_root() -> dict[str, Any]:
    """Process-only liveness. No dependencies of any kind."""
    return api_success(LivenessData().model_dump())


@router.get("/live", include_in_schema=False)
async def live() -> dict[str, Any]:
    """Liveness under the API prefix — identical to the root probe."""
    return api_success(LivenessData().model_dump())


@router.get("/ready")
async def ready(request: Request, settings: SettingsDep) -> JSONResponse:
    """Readiness: pings enabled dependencies; disabled ones degrade to 200."""
    readiness = await _readiness(request, settings)
    status_code = 503 if readiness.status == "error" else 200
    return JSONResponse(status_code=status_code, content=api_success(readiness.model_dump()))


@router.get("/deep")
async def deep(request: Request, settings: SettingsDep) -> JSONResponse:
    """Extended checks placeholder: pool stats, migration state arrive later."""
    readiness = await _readiness(request, settings)
    data = DeepHealthData(status=readiness.status, components=readiness.components, checks={})
    status_code = 503 if readiness.status == "error" else 200
    return JSONResponse(status_code=status_code, content=api_success(data.model_dump()))
