"""FastAPI lifespan: the only place process resources start and stop."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.bootstrap.container import Container
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the container, start it, expose it on `app.state`, and tear it down."""
    container = Container.build(get_settings())
    await container.startup()
    app.state.container = container
    try:
        yield
    finally:
        await container.shutdown()
        app.state.container = None
