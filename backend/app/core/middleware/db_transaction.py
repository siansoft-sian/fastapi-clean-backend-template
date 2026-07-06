"""Request-scoped DB transaction — no-op stub, registered so the stack order is fixed.

The real middleware (M2, with the asyncpg pool) acquires a connection, opens a
transaction for mutating requests, and commits/rolls back based on the outcome.
Innermost: nothing should run outside the transaction except the boundary itself.
"""

from starlette.types import ASGIApp, Receive, Scope, Send


class DBTransactionMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)
