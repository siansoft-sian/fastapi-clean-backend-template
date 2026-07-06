"""FastAPI lifespan: the only place process resources start and stop."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.bootstrap.container import Container
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the container, start it, expose its resources on `app.state`.

    `transaction_manager`/`db_pool` are None unless STARTUP_CONNECT_DATABASE
    is true — downstream code must never assume they exist unconditionally.
    """
    container = Container.build(get_settings())
    await container.startup()
    app.state.container = container
    app.state.transaction_manager = container.transaction_manager
    app.state.db_pool = container.database.pool if container.database is not None else None
    app.state.supabase_auth_client = container.supabase_auth_client
    app.state.jwks_client = container.jwks_client
    app.state.authorization_service = container.authorization_service
    app.state.redis_client = container.redis_client
    app.state.rate_limiter = container.rate_limiter
    try:
        yield
    finally:
        await container.shutdown()
        app.state.container = None
        app.state.transaction_manager = None
        app.state.db_pool = None
        app.state.supabase_auth_client = None
        app.state.jwks_client = None
        app.state.authorization_service = None
        app.state.redis_client = None
        app.state.rate_limiter = None
