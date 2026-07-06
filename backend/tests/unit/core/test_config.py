"""Settings: env mapping, defaults, empty-secret normalization, caching."""

import pytest

from app.core.config import Settings, get_settings
from app.core.enums import Environment


def test_fixture_env_is_picked_up() -> None:
    settings = get_settings()
    assert settings.app_env is Environment.TESTING
    assert settings.db_provider == "sqlite"
    assert settings.startup_connect_database is False
    assert settings.startup_connect_redis is False
    assert settings.startup_load_casbin is False
    assert settings.startup_create_celery is False


def test_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "renamed-service")
    monkeypatch.setenv("API_PREFIX", "/api/v2")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.app_name == "renamed-service"
    assert settings.api_prefix == "/api/v2"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_blank_secret_urls_normalize_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_DATABASE_URL", "")
    monkeypatch.setenv("REDIS_URL", " ")
    monkeypatch.setenv("SENTRY_DSN", "")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.postgres_database_url is None
    assert settings.redis_url is None
    assert settings.sentry_dsn is None


def test_secret_values_do_not_leak_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_DATABASE_URL", "postgresql://user:hunter2@db:5432/x")
    get_settings.cache_clear()
    settings = get_settings()
    assert "hunter2" not in repr(settings)
    assert settings.postgres_database_url is not None
    assert "hunter2" in settings.postgres_database_url.get_secret_value()


def test_is_production_flag() -> None:
    assert Settings(app_env=Environment.PRODUCTION).is_production is True
    assert Settings(app_env=Environment.TESTING).is_production is False
