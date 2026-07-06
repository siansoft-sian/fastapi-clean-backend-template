"""Application factory. `create_app()` builds the FastAPI app; it performs no I/O.

The uvicorn runner lives in `app/main.py`. Never merge the two.
"""

import structlog
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.bootstrap.lifespan import lifespan
from app.core.config import Settings, get_settings
from app.core.errors.exception_handlers import register_exception_handlers


def init_sentry(settings: Settings) -> None:
    """Sentry stub: a no-op when the DSN is empty; SDK wiring arrives with observability."""
    if settings.sentry_dsn is None:
        return
    structlog.get_logger(__name__).warning("sentry_dsn_configured_but_sdk_not_wired_yet")


def create_app() -> FastAPI:
    """Build and wire the application. Import-time safe: no network, DB, or Redis I/O."""
    settings = get_settings()
    init_sentry(settings)

    docs_enabled = not settings.is_production
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        default_response_class=ORJSONResponse,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    register_exception_handlers(app)
    return app


app = create_app()
