"""Request-scoped DB connection + transaction (real since M2).

Pass-through when the database is disabled (STARTUP_CONNECT_DATABASE=false).
Otherwise:

- Mutating verbs (POST/PUT/PATCH/DELETE) run inside ONE transaction shared by
  every repository call in the request: COMMIT only when the response is 2xx,
  ROLLBACK otherwise — including AppErrors that the inner exception handlers
  already converted into error responses.
- Reads (GET/HEAD/OPTIONS) get a plain pooled connection, no transaction.

The connection is stashed on `request.state.db_connection`; handlers reach it
via `api.deps.get_db_connection`. Delegates all transaction semantics to the
transaction manager — no commit/rollback logic lives here.

Limitation (by design for the envelope-based template): responses must be
fully materialized before this middleware returns; an endpoint streaming rows
would outlive the connection scope.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class _Rollback(Exception):
    """Internal control flow: forces the transaction context manager to roll
    back while still returning the already-built (error) response."""

    def __init__(self, response: Response) -> None:
        self.response = response


class DBTransactionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        manager = getattr(request.app.state, "transaction_manager", None)
        if manager is None:
            return await call_next(request)

        if request.method not in MUTATING_METHODS:
            async with manager.connection() as connection:
                request.state.db_connection = connection
                return await call_next(request)

        try:
            async with manager.transaction() as connection:
                request.state.db_connection = connection
                response = await call_next(request)
                if response.status_code >= 300:
                    raise _Rollback(response)
                return response
        except _Rollback as signal:
            return signal.response
