"""Auth error family — extends the core AppError taxonomy.

All of these flow through the M1 exception boundary and leave as the standard
envelope. Messages stay generic: never include tokens, cookie values, or the
PKCE verifier.
"""

from app.core.enums import ErrorCategory
from app.core.errors import error_codes
from app.core.errors.core_errors import (
    AppError,
    ExternalServiceError,
    ForbiddenError,
    UnauthorizedError,
)


class AuthenticationRequiredError(UnauthorizedError):
    code = error_codes.AUTHENTICATION_REQUIRED
    default_message = "Authentication required"


class InvalidSessionError(UnauthorizedError):
    code = error_codes.INVALID_SESSION
    default_message = "Session is invalid"


class SessionExpiredError(UnauthorizedError):
    code = error_codes.SESSION_EXPIRED
    default_message = "Session has expired"


class TokenVerificationError(UnauthorizedError):
    """A GoTrue access token failed server-side verification (signature/claims)."""

    code = error_codes.TOKEN_VERIFICATION_FAILED
    default_message = "Token verification failed"


class CsrfValidationError(ForbiddenError):
    code = error_codes.CSRF_VALIDATION_FAILED
    default_message = "CSRF validation failed"


class OAuthExchangeError(ExternalServiceError):
    code = error_codes.OAUTH_EXCHANGE_FAILED
    default_message = "Authentication provider request failed"


class IdentityMappingError(AppError):
    code = error_codes.IDENTITY_MAPPING_FAILED
    http_status = 500
    category = ErrorCategory.INTERNAL
    default_message = "Identity could not be mapped to an internal user"
