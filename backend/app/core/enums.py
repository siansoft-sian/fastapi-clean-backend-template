"""Cross-cutting enumerations. Business enums live in their own module."""

from enum import StrEnum


class Environment(StrEnum):
    """Deployment environment the process runs in."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class ErrorCategory(StrEnum):
    """Coarse error classification carried in `meta.category` of error envelopes."""

    AUTH = "auth"
    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMIT = "rate_limit"
    DATABASE = "database"
    EXTERNAL = "external"
    INTERNAL = "internal"
    HTTP = "http"
