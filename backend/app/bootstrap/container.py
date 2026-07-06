"""Process-lifetime resource container (DB pool, Redis, Casbin, Celery).

Nothing here runs at import time. `startup()` touches only the resources whose
`startup_*` flag is enabled; with all flags off (the default) the container
starts and stops without performing any I/O.

M2: the database path is real — `startup_connect_database=true` builds and
connects the asyncpg pool and its transaction manager. Redis/Casbin/Celery
still fail loudly until their milestones ship.
"""

from __future__ import annotations

import httpx
import structlog

from app.auth.jwks_client import JwksClient
from app.auth.supabase_auth_client import DEFAULT_TIMEOUT, SupabaseAuthClient
from app.core.config import Settings
from app.db.connection import DatabasePool
from app.db.transaction_manager import AsyncpgTransactionManager

logger = structlog.get_logger(__name__)


class Container:
    """Owns process-lifetime resources and controls their lifecycle."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.database: DatabasePool | None = None
        self.transaction_manager: AsyncpgTransactionManager | None = None
        self.supabase_auth_client: SupabaseAuthClient | None = None
        self.jwks_client: JwksClient | None = None
        self._gotrue_http: httpx.AsyncClient | None = None
        self.redis: object | None = None
        self.casbin_enforcer: object | None = None
        self.celery_app: object | None = None
        self._started = False

    @classmethod
    def build(cls, settings: Settings) -> Container:
        """Construct the container without touching any external resource."""
        return cls(settings=settings)

    async def startup(self) -> None:
        """Initialize resources whose startup flag is enabled. No flag, no I/O.

        Flags whose adapters have not shipped yet fail loudly instead of
        pretending a resource exists.
        """
        if self._started:
            return
        if self.settings.startup_connect_database:
            self.database = DatabasePool.from_settings(self.settings)
            await self.database.connect()
            self.transaction_manager = AsyncpgTransactionManager(self.database)
        # GoTrue + JWKS clients: constructing them opens no sockets, so they
        # are created whenever configured; only the JWKS PRELOAD does I/O and
        # stays behind its startup flag.
        settings = self.settings
        if (
            settings.supabase_project_url
            and settings.supabase_anon_key
            and settings.oauth_redirect_uri
        ):
            self._gotrue_http = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
            self.supabase_auth_client = SupabaseAuthClient(
                http_client=self._gotrue_http,
                project_url=settings.supabase_project_url,
                anon_key=settings.supabase_anon_key.get_secret_value(),
                redirect_uri=settings.oauth_redirect_uri,
                provider=settings.oauth_provider,
            )
        if settings.supabase_jwks_url:
            self.jwks_client = JwksClient(
                jwks_url=settings.supabase_jwks_url,
                cache_ttl_seconds=settings.jwks_cache_ttl_seconds,
            )
            if settings.startup_preload_jwks:
                await self.jwks_client.preload()
        if self.settings.startup_connect_redis:
            raise NotImplementedError(
                "STARTUP_CONNECT_REDIS=true, but the Redis adapter has not shipped yet. "
                "Set the flag to false."
            )
        if self.settings.startup_load_casbin:
            raise NotImplementedError(
                "STARTUP_LOAD_CASBIN=true, but the Casbin enforcer has not shipped yet. "
                "Set the flag to false."
            )
        if self.settings.startup_create_celery:
            raise NotImplementedError(
                "STARTUP_CREATE_CELERY=true, but the Celery app has not shipped yet. "
                "Set the flag to false."
            )
        self._started = True
        logger.info(
            "container_started",
            database=self.settings.startup_connect_database,
            redis=self.settings.startup_connect_redis,
            casbin=self.settings.startup_load_casbin,
            celery=self.settings.startup_create_celery,
        )

    async def shutdown(self) -> None:
        """Release resources in reverse acquisition order. Safe to call when idle."""
        if not self._started:
            return
        if self._gotrue_http is not None:
            await self._gotrue_http.aclose()
        self._gotrue_http = None
        self.supabase_auth_client = None
        self.jwks_client = None
        if self.database is not None:
            await self.database.disconnect()
        self.transaction_manager = None
        self.database = None
        self._started = False
        logger.info("container_stopped")
