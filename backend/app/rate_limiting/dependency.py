"""Per-scope rate limiting as a FastAPI dependency (post-auth).

`rate_limit("booking.create")` returns a dependency for the route's
`dependencies=[...]` list. USER/TENANT-scoped rules resolve the principal via
`get_current_principal` (FastAPI caches it per request and honors test
overrides), so place the auth guard alongside it. IP/ROUTE/RESOURCE/ACTION
scopes need only the request. No-op when rate limiting is disabled or no
limiter is available.

v1 identifier semantics (documented, tunable): ROUTE and RESOURCE key on the
request path (RESOURCE paths include the id path-param); ACTION is one global
bucket — the rule name already names the action.
"""

from collections.abc import Callable, Coroutine
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Request

from app.auth.auth_context import AuthContext
from app.auth.dependencies import get_current_principal
from app.bootstrap.factories import provide_rate_limiter
from app.core.config import get_settings
from app.rate_limiting.client_ip import parse_trusted_proxies, resolve_client_ip
from app.rate_limiting.rules import RateLimitScope, get_rule

_trusted_proxies = lru_cache(maxsize=4)(parse_trusted_proxies)

_limiter = provide_rate_limiter  # DI seam: the factory owns limiter resolution


def _request_identifier(scope: RateLimitScope, request: Request) -> str:
    if scope is RateLimitScope.IP:
        return resolve_client_ip(
            request.client.host if request.client else None,
            request.headers.get("x-forwarded-for"),
            _trusted_proxies(get_settings().trusted_proxies),
        )
    if scope in (RateLimitScope.ROUTE, RateLimitScope.RESOURCE):
        return request.url.path
    return "all"  # ACTION: one global bucket per rule


def rate_limit(rule_name: str) -> Callable[..., Coroutine[Any, Any, None]]:
    """Dependency factory; unknown rule names fail at router-definition time.

    Only the SCOPE is captured here (it selects the dependency signature);
    limit/window are re-read from the registry per request so limits stay
    tunable at runtime — same behavior as the middleware.
    """
    scope = get_rule(rule_name).scope  # eager validation

    if scope in (RateLimitScope.USER, RateLimitScope.TENANT):

        async def _enforce_for_principal(
            request: Request,
            principal: Annotated[AuthContext, Depends(get_current_principal)],
        ) -> None:
            limiter = _limiter(request)
            if limiter is None:
                return
            rule = get_rule(rule_name)
            identifier = (
                principal.user_id if rule.scope is RateLimitScope.USER else principal.tenant_id
            )
            await limiter.enforce(rule, identifier)

        return _enforce_for_principal

    async def _enforce_for_request(request: Request) -> None:
        limiter = _limiter(request)
        if limiter is None:
            return
        rule = get_rule(rule_name)
        await limiter.enforce(rule, _request_identifier(rule.scope, request))

    return _enforce_for_request
