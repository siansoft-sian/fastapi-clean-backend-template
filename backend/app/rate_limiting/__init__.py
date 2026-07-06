"""Hybrid rate limiting (M5).

- Global IP ceiling: middleware, pre-auth — coarse flood protection for every
  route (including unauthenticated auth endpoints) keyed only by client IP.
- Per-scope limits: the `rate_limit(rule)` dependency, post-auth — keyed by
  user/tenant/action/resource via AuthContext.

One limiter core serves both. Pure modules (keys, rules, backend, limiter,
client_ip) import no FastAPI — enforced by import-linter; only dependency.py
and core/middleware/rate_limit.py touch the framework.
"""
