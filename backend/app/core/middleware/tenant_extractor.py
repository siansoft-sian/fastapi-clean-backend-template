"""Tenant extraction — no-op stub, registered so the stack order is fixed early.

The real middleware (tenancy milestone) resolves the tenant from the validated
`X-Tenant-Id` header / JWT claims and binds it to the tenant contextvar.
"""

from starlette.types import ASGIApp, Receive, Scope, Send


class TenantExtractorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)
