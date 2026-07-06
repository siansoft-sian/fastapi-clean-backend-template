"""Idempotency-Key handling — no-op stub, registered so the stack order is fixed.

The real middleware (idempotency milestone) detects replayed mutating requests
by their `Idempotency-Key` header and short-circuits with the stored response.
"""

from starlette.types import ASGIApp, Receive, Scope, Send


class IdempotencyMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)
