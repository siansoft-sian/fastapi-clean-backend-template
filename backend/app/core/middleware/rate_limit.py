"""Global IP-ceiling rate limiting (pre-auth). Real since M5.

Applies the `global.ip` rule keyed by client IP to EVERY request before
routing/auth — flood protection for unauthenticated endpoints included.
Per-user/tenant limits do NOT belong here (no principal exists yet); they
live in `app/rate_limiting/dependency.py`.

Health probes are exempt. Pass-through when rate limiting is disabled or no
limiter was built (flag off, nothing injected). Runs outside the
exception-handler stack, so denials build their 429 envelope inline, sharing
`rate_limit_headers()` with the handler.
"""

from functools import lru_cache

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.enums import ErrorCategory
from app.core.errors.core_errors import RateLimitExceededError
from app.core.errors.exception_handlers import rate_limit_headers
from app.core.responses import api_error
from app.rate_limiting.client_ip import parse_trusted_proxies, resolve_client_ip
from app.rate_limiting.rules import GLOBAL_IP_RULE_NAME, get_rule

_trusted_proxies = lru_cache(maxsize=4)(parse_trusted_proxies)


def _is_exempt(path: str, api_prefix: str) -> bool:
    """Liveness/readiness must never be rate-limited."""
    return path.startswith("/health") or path.startswith(f"{api_prefix}/health")


def _rate_limited_response(request: Request, exc: RateLimitExceededError) -> JSONResponse:
    body = api_error(
        exc.code,
        exc.message,
        details=exc.details,
        meta={
            "path": request.url.path,
            "method": request.method,
            "category": ErrorCategory.RATE_LIMIT.value,
        },
    )
    return JSONResponse(status_code=exc.http_status, content=body, headers=rate_limit_headers(exc))


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        limiter = getattr(request.app.state, "rate_limiter", None)
        settings = get_settings()
        if limiter is None or not settings.rate_limit_enabled:
            return await call_next(request)
        if _is_exempt(request.url.path, settings.api_prefix):
            return await call_next(request)

        identifier = resolve_client_ip(
            request.client.host if request.client else None,
            request.headers.get("x-forwarded-for"),
            _trusted_proxies(settings.trusted_proxies),
        )
        rule = get_rule(GLOBAL_IP_RULE_NAME)
        try:
            decision = await limiter.check(rule, identifier)
        except RateLimitExceededError as exc:
            # Fail-closed backend failure surfaced by the limiter.
            return _rate_limited_response(request, exc)
        if not decision.allowed:
            return _rate_limited_response(
                request,
                RateLimitExceededError(
                    details={"rule": rule.name},
                    retry_after=decision.reset_after_seconds,
                    limit=decision.limit,
                    remaining=decision.remaining,
                ),
            )
        return await call_next(request)
