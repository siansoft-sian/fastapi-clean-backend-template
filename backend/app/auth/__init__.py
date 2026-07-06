"""Authentication — locked BFF pattern (D11).

FastAPI is the sole auth gateway: all Supabase GoTrue interactions happen
server-to-server; the browser holds only an HttpOnly opaque-session-id cookie
plus a readable CSRF cookie. No token ever reaches the client.

Layering inside this package:
- pure / framework-free: csrf, pkce, jwks_client, jwt_verifier,
  supabase_auth_client, session_repository, identity_mapper, auth_context,
  exceptions, scopes (enforced by an import-linter contract)
- FastAPI-facing: cookies, dependencies, routes

Auth is enforced with per-route Depends() — never middleware.
"""
