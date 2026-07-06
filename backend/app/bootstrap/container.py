"""Process-lifetime resource container (DB pool, Redis, Casbin, Celery).

Nothing here runs at import time. `startup()` touches only the resources whose
`startup_*` flag is enabled; with all flags off (the default) the container
starts and stops without performing any I/O. Real adapters arrive in later
milestones — the asyncpg pool lands in M2.
"""

from __future__ import annotations

import structlog

from app.core.config import Settings

logger = structlog.get_logger(__name__)


class Container:
    """Owns process-lifetime resources and controls their lifecycle."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_pool: object | None = None
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
            raise NotImplementedError(
                "STARTUP_CONNECT_DATABASE=true, but the asyncpg pool adapter arrives in M2. "
                "Set the flag to false."
            )
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
        # Reverse order of startup(); nothing to release until adapters ship in M2+.
        self._started = False
        logger.info("container_stopped")
