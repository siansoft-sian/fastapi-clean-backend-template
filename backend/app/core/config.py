"""Application settings loaded from environment variables (and `.env` in development).

`get_settings()` is the only sanctioned accessor. It is cached so the environment
is read once per process; tests mutate `os.environ` and call
`get_settings.cache_clear()` to re-read.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import Environment


class Settings(BaseSettings):
    """Process configuration. Reading it must never perform I/O beyond the env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "fastapi-clean-backend"
    app_env: Environment = Environment.DEVELOPMENT
    app_debug: bool = False
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"

    # --- Server (used by the uvicorn runner only) ---
    server_host: str = "0.0.0.0"  # noqa: S104 — container-friendly default
    server_port: int = 8000

    # --- Database (Track A: asyncpg + Postgres behind repository ports) ---
    # Selects the adapter wired in the composition root; application code never sees it.
    db_provider: Literal["postgres", "sqlite"] = "sqlite"
    postgres_database_url: SecretStr | None = None
    sqlite_database_url: str = "./local.db"
    db_pool_min_size: int = 2
    db_pool_max_size: int = 10
    db_command_timeout: int = 30

    # --- Redis ---
    redis_url: SecretStr | None = None

    # --- Rate limiting (M5 hybrid: IP-ceiling middleware + per-scope dependency) ---
    rate_limit_enabled: bool = True
    # Global default when Redis is down: allow + log loudly. Sensitive rules
    # (auth, refund) opt into fail-closed per rule. A stored decision, never
    # an accident.
    rate_limit_fail_open: bool = True
    # Comma-separated IPs/CIDRs of proxies whose X-Forwarded-For is trusted.
    # Empty (default) = never trust XFF; the socket peer address is used.
    trusted_proxies: str = ""

    # --- Auth: Supabase GoTrue (BFF — all interactions are server-to-server) ---
    supabase_project_url: str | None = None
    supabase_anon_key: SecretStr | None = None
    supabase_jwks_url: str | None = None
    supabase_jwt_issuer: str | None = None
    supabase_jwt_audience: str = "authenticated"
    oauth_provider: str = "google"
    oauth_redirect_uri: str | None = None
    frontend_post_login_url: str = "http://localhost:3000/"
    jwks_cache_ttl_seconds: int = 3600

    # --- Session store (BFF: opaque hashed token; tokens never reach the browser) ---
    # Fernet key for app-level encryption of GoTrue tokens at rest (Decision A).
    # Generate with app.auth.token_cipher.TokenCipher.generate_key().
    session_token_encryption_key: SecretStr | None = None
    identity_auto_provision: bool = False

    # --- Session cookies ---
    session_cookie_name: str = "sid"
    session_cookie_secure: bool = True
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_cookie_domain: str | None = None
    session_absolute_ttl_seconds: int = 43200  # 12h
    session_idle_ttl_seconds: int = 1800  # 30min, slides on each authenticated request

    # --- CSRF (double-submit cookie) ---
    csrf_cookie_name: str = "csrftoken"
    csrf_header_name: str = "X-CSRF-Token"

    # --- PKCE login flow ---
    pkce_state_cookie_name: str = "auth_state"
    pkce_state_ttl_seconds: int = 600

    # --- Authorization ---
    casbin_model_path: str = "app/authorization/casbin_model.conf"
    casbin_policy_path: str = "app/authorization/policy.csv"

    # --- Observability ---
    sentry_dsn: SecretStr | None = None
    log_level: str = "INFO"

    # --- Startup flags: nothing connects unless explicitly enabled ---
    startup_connect_database: bool = False
    startup_connect_redis: bool = False
    startup_load_casbin: bool = False
    startup_create_celery: bool = False
    startup_preload_jwks: bool = False

    @field_validator(
        "postgres_database_url",
        "redis_url",
        "sentry_dsn",
        "supabase_project_url",
        "supabase_anon_key",
        "supabase_jwks_url",
        "supabase_jwt_issuer",
        "oauth_redirect_uri",
        "session_cookie_domain",
        "session_token_encryption_key",
        mode="before",
    )
    @classmethod
    def _empty_string_is_none(cls, value: object) -> object:
        """Treat blank env values (`POSTGRES_DATABASE_URL=`) as unset."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env is Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    """Return process-wide settings, reading the environment exactly once."""
    return Settings()
