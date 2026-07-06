"""Middleware assembly. The order is explicit and load-bearing.

Request flow (outermost first):

    request_context        request id + timing; everything below logs under it
      -> http_logging      access log with request_id and duration
        -> security_headers
          -> tenant_extractor   (stub) tenant known before limiting/idempotency
            -> rate_limit       (stub) reject early, per tenant
              -> idempotency    (stub) replay detection after limiter, before tx
                -> db_transaction (stub) innermost: request-scoped transaction
                  -> router / endpoint

`add_middleware` is LIFO — the LAST one added runs OUTERMOST — so the calls
below are in reverse of the flow above. Keep both in sync when editing.
"""

from fastapi import FastAPI

from app.core.middleware.db_transaction import DBTransactionMiddleware
from app.core.middleware.http_logging import HTTPLoggingMiddleware
from app.core.middleware.idempotency import IdempotencyMiddleware
from app.core.middleware.rate_limit import RateLimitMiddleware
from app.core.middleware.request_context import RequestContextMiddleware
from app.core.middleware.security_headers import SecurityHeadersMiddleware
from app.core.middleware.tenant_extractor import TenantExtractorMiddleware


def install_middleware(app: FastAPI) -> None:
    """Install the full stack in the documented order."""
    app.add_middleware(DBTransactionMiddleware)
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(TenantExtractorMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(HTTPLoggingMiddleware)
    app.add_middleware(RequestContextMiddleware)
