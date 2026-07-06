"""DI composition root: provider functions consumed by the API boundary.

Services are constructed HERE, with repositories and clients injected through
their constructors. Routers receive them via `Depends(provide_<service>)` —
never `Depends(SomeServiceClass)`, never construction inside handlers.

Shape of a service provider (arrives with the first real module):

    def provide_booking_service(request: Request) -> BookingService:
        manager = provide_transaction_manager(request)
        return BookingService(bookings=PostgresBookingRepository(manager))
"""

from fastapi import Request

from app.auth.identity_mapper import (
    AsyncpgIdentityMapper,
    IdentityMapperProtocol,
)
from app.auth.jwks_client import JwksClient
from app.auth.jwt_verifier import JwtVerifier
from app.auth.session_repository import (
    AsyncpgSessionRepository,
    SessionRepositoryProtocol,
)
from app.auth.supabase_auth_client import SupabaseAuthClient
from app.auth.token_cipher import TokenCipher
from app.authorization.authorization_service import AuthorizationService
from app.authorization.casbin_enforcer import CasbinEnforcer
from app.core.config import get_settings
from app.db.transaction_manager import TransactionManagerProtocol
from app.modules.bookings.application.use_cases.approve_booking import ApproveBookingUseCase
from app.modules.bookings.application.use_cases.cancel_booking import CancelBookingUseCase
from app.modules.bookings.application.use_cases.create_booking import CreateBookingUseCase
from app.modules.bookings.application.use_cases.get_booking import GetBookingUseCase
from app.modules.bookings.infrastructure.authorization_adapter import AuthorizationAdapter
from app.modules.bookings.infrastructure.database_booking_repository import (
    DatabaseBookingRepository,
)
from app.modules.bookings.infrastructure.outbox_adapter import LoggingOutboxAdapter
from app.modules.bookings.ports.booking_repository import BookingRepositoryProtocol
from app.modules.bookings.ports.outbox import OutboxPort
from app.rate_limiting.limiter import RateLimiter


def provide_transaction_manager(request: Request) -> TransactionManagerProtocol:
    """The process-wide transaction manager created by container.startup().

    Raises when the database path is disabled — reaching this with
    STARTUP_CONNECT_DATABASE=false is a wiring bug (tests should inject a
    fake repository instead of touching the DB path).
    """
    manager = getattr(request.app.state, "transaction_manager", None)
    if manager is None:
        raise RuntimeError(
            "Transaction manager requested but the database is not connected. "
            "Set STARTUP_CONNECT_DATABASE=true and POSTGRES_DATABASE_URL, or inject "
            "a fake repository in tests."
        )
    return manager


def _require_pool(request: Request, what: str) -> object:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise RuntimeError(
            f"{what} requested but the database is not connected. Set "
            "STARTUP_CONNECT_DATABASE=true, or inject a fake on app.state in tests."
        )
    return pool


def provide_session_repository(request: Request) -> SessionRepositoryProtocol:
    """Server-side session store. Tests inject `app.state.session_repository`.

    The real adapter needs the Fernet cipher for GoTrue-token encryption at
    rest (Decision A) — a missing key is a wiring error, not a 401.
    """
    existing = getattr(request.app.state, "session_repository", None)
    if existing is not None:
        return existing
    settings = get_settings()
    if settings.session_token_encryption_key is None:
        raise RuntimeError(
            "SESSION_TOKEN_ENCRYPTION_KEY is required when the database session "
            "store is enabled. Generate one with: python -c "
            '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    cipher = TokenCipher(settings.session_token_encryption_key.get_secret_value())
    repository = AsyncpgSessionRepository(_require_pool(request, "Session repository"), cipher)
    request.app.state.session_repository = repository
    return repository


def provide_identity_mapper(request: Request) -> IdentityMapperProtocol:
    """GoTrue-subject -> internal identity. Tests inject `app.state.identity_mapper`."""
    existing = getattr(request.app.state, "identity_mapper", None)
    if existing is not None:
        return existing
    mapper = AsyncpgIdentityMapper(_require_pool(request, "Identity mapper"))
    request.app.state.identity_mapper = mapper
    return mapper


def provide_rate_limiter(request: Request) -> RateLimiter | None:
    """The process-wide limiter, or None (= rate limiting pass-through).

    container.startup() builds it when STARTUP_CONNECT_REDIS=true; tests
    inject a fake-backed limiter via `app.state.rate_limiter`. Returning None
    is legitimate — both consumers treat it as disabled (invariant 4).
    """
    if not get_settings().rate_limit_enabled:
        return None
    limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    return limiter


def provide_authorization_service(request: Request) -> AuthorizationService:
    """Layer-2 authorization service (Casbin-backed).

    container.startup() builds it when STARTUP_LOAD_CASBIN=true (fail-fast on
    a broken policy). When absent — e.g. test transports that skip lifespan —
    it is built lazily here: a local model/policy file read, no network I/O.
    Tests may inject a stub via `app.state.authorization_service`.
    """
    existing = getattr(request.app.state, "authorization_service", None)
    if existing is not None:
        return existing
    service = AuthorizationService(CasbinEnforcer.from_settings(get_settings()))
    request.app.state.authorization_service = service
    return service


def provide_supabase_auth_client(request: Request) -> SupabaseAuthClient:
    """GoTrue S2S client, created by container.startup(). Tests inject a fake."""
    client = getattr(request.app.state, "supabase_auth_client", None)
    if client is None:
        raise RuntimeError(
            "Supabase auth client is not configured. Set SUPABASE_PROJECT_URL, "
            "SUPABASE_ANON_KEY and OAUTH_REDIRECT_URI, or inject a fake on app.state."
        )
    return client


# --- bookings module wiring (the reference pattern for future modules) ---


def _booking_repository(request: Request) -> BookingRepositoryProtocol:
    """Tests inject `app.state.booking_repository` (the in-memory fake)."""
    existing = getattr(request.app.state, "booking_repository", None)
    if existing is not None:
        return existing
    repository = DatabaseBookingRepository(_require_pool(request, "Booking repository"))
    request.app.state.booking_repository = repository
    return repository


def _booking_outbox(request: Request) -> OutboxPort:
    """# TODO(M7-outbox): swap for the transactional outbox adapter here —
    use cases already emit through the port, so M7 is wiring-only."""
    existing = getattr(request.app.state, "booking_outbox", None)
    if existing is not None:
        return existing
    outbox = LoggingOutboxAdapter()
    request.app.state.booking_outbox = outbox
    return outbox


def _booking_authorization(request: Request) -> AuthorizationAdapter:
    return AuthorizationAdapter(provide_authorization_service(request))


def provide_create_booking_use_case(request: Request) -> CreateBookingUseCase:
    return CreateBookingUseCase(
        repository=_booking_repository(request),
        authorization=_booking_authorization(request),
        outbox=_booking_outbox(request),
    )


def provide_get_booking_use_case(request: Request) -> GetBookingUseCase:
    return GetBookingUseCase(
        repository=_booking_repository(request),
        authorization=_booking_authorization(request),
    )


def provide_approve_booking_use_case(request: Request) -> ApproveBookingUseCase:
    return ApproveBookingUseCase(
        repository=_booking_repository(request),
        authorization=_booking_authorization(request),
        outbox=_booking_outbox(request),
    )


def provide_cancel_booking_use_case(request: Request) -> CancelBookingUseCase:
    return CancelBookingUseCase(
        repository=_booking_repository(request),
        authorization=_booking_authorization(request),
        outbox=_booking_outbox(request),
    )


def provide_jwt_verifier(request: Request) -> JwtVerifier:
    """Server-side GoTrue access-token verifier (JWKS-backed)."""
    existing = getattr(request.app.state, "jwt_verifier", None)
    if existing is not None:
        return existing
    jwks_client: JwksClient | None = getattr(request.app.state, "jwks_client", None)
    settings = request.app.state.container.settings
    if jwks_client is None or settings.supabase_jwt_issuer is None:
        raise RuntimeError(
            "JWT verifier requested but JWKS is not configured. Set "
            "SUPABASE_JWKS_URL and SUPABASE_JWT_ISSUER."
        )
    verifier = JwtVerifier(
        jwks_client=jwks_client,
        issuer=settings.supabase_jwt_issuer,
        audience=settings.supabase_jwt_audience,
    )
    request.app.state.jwt_verifier = verifier
    return verifier
