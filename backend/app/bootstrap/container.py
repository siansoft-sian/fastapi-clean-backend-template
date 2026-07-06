"""Process-lifetime resource container (DB pool, Redis, Casbin, Celery).

Nothing here runs at import time. `startup()` touches only the resources whose
`startup_*` flag is enabled; with all flags off (the default) the container
starts and stops without performing any I/O.

M2: the database path is real — `startup_connect_database=true` builds and
connects the asyncpg pool and its transaction manager. Redis/Casbin/Celery
still fail loudly until their milestones ship.
"""

from __future__ import annotations

import structlog

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
        if self.database is not None:
            await self.database.disconnect()
        self.transaction_manager = None
        self.database = None
        self._started = False
        logger.info("container_stopped")
