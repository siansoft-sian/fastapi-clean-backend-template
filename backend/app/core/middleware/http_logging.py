"""Access logging: one `request_completed` event per request, with duration.

Sits just inside `RequestContextMiddleware` so every event carries the
request id. Logs in a `finally` so failed requests are recorded too.
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.context import get_request_id
from app.core.logging.request_logging import log_request_completed


class HTTPLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        status_code = 500  # what the client sees if call_next raises
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            log_request_completed(
                request_id=get_request_id(),
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
            )
