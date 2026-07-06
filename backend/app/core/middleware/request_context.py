"""Outermost middleware: request id, timing, contextvar binding, X-Request-ID header.

The contextvar is deliberately NOT reset on the way out: Starlette's catch-all
500 handler runs outside the user middleware stack, and it still needs the id
to build its envelope. Each request runs in its own task (fresh context), and
`clear_contextvars()` at entry guards against any reuse.
"""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.constants import REQUEST_ID_HEADER
from app.core.context import request_id_var


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Generates or propagates the request id and times the request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        request_id_var.set(request_id)
        request.state.request_id = request_id

        start = time.perf_counter()
        response = await call_next(request)
        request.state.duration_ms = round((time.perf_counter() - start) * 1000, 2)

        response.headers[REQUEST_ID_HEADER] = request_id
        return response
