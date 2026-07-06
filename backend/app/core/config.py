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

    # --- Redis ---
    redis_url: SecretStr | None = None

    # --- Auth (Supabase JWT via JWKS) ---
    supabase_jwks_url: str | None = None
    supabase_jwt_issuer: str | None = None
    supabase_jwt_audience: str = "authenticated"

    # --- Authorization ---
    casbin_model_path: str = "app/authorization/casbin_model.conf"

    # --- Observability ---
    sentry_dsn: SecretStr | None = None
    log_level: str = "INFO"

    # --- Startup flags: nothing connects unless explicitly enabled ---
    startup_connect_database: bool = False
    startup_connect_redis: bool = False
    startup_load_casbin: bool = False
    startup_create_celery: bool = False

    @field_validator(
        "postgres_database_url",
        "redis_url",
        "sentry_dsn",
        "supabase_jwks_url",
        "supabase_jwt_issuer",
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
