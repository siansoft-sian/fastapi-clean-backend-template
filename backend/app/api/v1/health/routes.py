"""Health endpoints.

Liveness is process-only (no dependencies, hidden from the schema, bypasses
auth). Readiness honors the STARTUP_* flags: a dependency that is intentionally
disabled degrades the status (still 200) instead of failing the probe.
"""

from typing import Any, Literal

from fastapi import APIRouter

from app.api.deps import SettingsDep
from app.api.v1.health.schemas import DeepHealthData, LivenessData, ReadinessData
from app.core.config import Settings
from app.core.responses import api_success

# Mounted at the app root: the container HEALTHCHECK and orchestrators hit this.
root_router = APIRouter(include_in_schema=False)

# Mounted under settings.api_prefix in create_app().
router = APIRouter(prefix="/health", tags=["health"])


def _component_state(enabled: bool) -> str:
    # Real pings arrive with the adapters (asyncpg pool in M2). Until then an
    # enabled component is "unknown" rather than a pretend "ok".
    return "unknown" if enabled else "disabled"


def _readiness(settings: Settings) -> ReadinessData:
    components = {
        "database": _component_state(settings.startup_connect_database),
        "redis": _component_state(settings.startup_connect_redis),
        "casbin": _component_state(settings.startup_load_casbin),
        "jwks": _component_state(settings.supabase_jwks_url is not None),
    }
    all_ok = all(state == "ok" for state in components.values())
    status: Literal["ok", "degraded"] = "ok" if all_ok else "degraded"
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
async def ready(settings: SettingsDep) -> dict[str, Any]:
    """Readiness: DB ping + JWKS load once adapters exist; flags-off degrades to 200."""
    return api_success(_readiness(settings).model_dump())


@router.get("/deep")
async def deep(settings: SettingsDep) -> dict[str, Any]:
    """Extended checks placeholder: pool stats, migration state, queue depth arrive M2+."""
    readiness = _readiness(settings)
    data = DeepHealthData(status=readiness.status, components=readiness.components, checks={})
    return api_success(data.model_dump())
