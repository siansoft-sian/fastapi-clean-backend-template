"""Rate limiting — no-op stub, registered so the stack order is fixed early.

The real middleware (rate-limit milestone) rejects over-limit requests with a
429 `RATE_LIMIT_EXCEEDED` envelope, keyed per tenant/principal.
"""

from starlette.types import ASGIApp, Receive, Scope, Send


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)
