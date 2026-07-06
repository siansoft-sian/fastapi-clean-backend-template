"""Boundary dependencies: configuration and request-scoped context.

Only delivery-layer concerns belong here (settings, auth context, pagination
parsing). Service providers live in `app/bootstrap/factories.py` — routers
never `Depends(SomeServiceClass)`.
"""

from typing import Annotated, Any

from fastapi import Depends, Request

from app.bootstrap.factories import provide_transaction_manager
from app.core.config import Settings, get_settings
from app.db.transaction_manager import TransactionManagerProtocol

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_db_connection(request: Request) -> Any:
    """Request-scoped DB connection placed by DBTransactionMiddleware.

    Mutating requests share one transaction through this connection. The
    object is opaque at this layer — only infrastructure adapters know its
    engine type. Raises when the database path is disabled: that is a wiring
    bug (inject a fake repository in tests instead).
    """
    connection = getattr(request.state, "db_connection", None)
    if connection is None:
        raise RuntimeError(
            "No request-scoped DB connection. Either STARTUP_CONNECT_DATABASE is "
            "false or DBTransactionMiddleware is not installed."
        )
    return connection


DbConnectionDep = Annotated[Any, Depends(get_db_connection)]
TransactionManagerDep = Annotated[TransactionManagerProtocol, Depends(provide_transaction_manager)]
