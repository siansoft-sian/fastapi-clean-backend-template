"""Application factory. `create_app()` builds the FastAPI app; it performs no I/O.

The uvicorn runner lives in `app/main.py`. Never merge the two.
"""

import structlog
from fastapi import FastAPI

from app.api.v1.health.routes import root_router as health_root_router
from app.api.v1.health.routes import router as health_router
from app.auth.routes import router as auth_router
from app.bootstrap.lifespan import lifespan
from app.core.config import Settings, get_settings
from app.core.errors.exception_handlers import register_exception_handlers
from app.core.logging.core_logging import configure_logging
from app.core.middleware import install_middleware
from app.modules._authz_demo.api.router import router as authz_demo_router
from app.modules.bookings.api.router import router as bookings_router


def init_sentry(settings: Settings) -> None:
    """Sentry stub: a no-op when the DSN is empty; SDK wiring arrives with observability."""
    if settings.sentry_dsn is None:
        return
    structlog.get_logger(__name__).warning("sentry_dsn_configured_but_sdk_not_wired_yet")


def create_app() -> FastAPI:
    """Build and wire the application. Import-time safe: no network, DB, or Redis I/O."""
    settings = get_settings()
    configure_logging(settings.log_level)
    init_sentry(settings)

    docs_enabled = not settings.is_production
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    install_middleware(app)
    register_exception_handlers(app)

    app.include_router(health_root_router)
    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(auth_router, prefix=settings.api_prefix)
    # Throwaway two-layer authorization proof (see modules/_authz_demo).
    app.include_router(authz_demo_router, prefix=settings.api_prefix)
    app.include_router(bookings_router, prefix=settings.api_prefix)
    return app


app = create_app()
