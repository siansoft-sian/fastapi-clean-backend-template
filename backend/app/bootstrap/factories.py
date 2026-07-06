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
from app.db.transaction_manager import TransactionManagerProtocol


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
    """Server-side session store. Tests inject `app.state.session_repository`."""
    existing = getattr(request.app.state, "session_repository", None)
    if existing is not None:
        return existing
    repository = AsyncpgSessionRepository(_require_pool(request, "Session repository"))
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


def provide_supabase_auth_client(request: Request) -> SupabaseAuthClient:
    """GoTrue S2S client, created by container.startup(). Tests inject a fake."""
    client = getattr(request.app.state, "supabase_auth_client", None)
    if client is None:
        raise RuntimeError(
            "Supabase auth client is not configured. Set SUPABASE_PROJECT_URL, "
            "SUPABASE_ANON_KEY and OAUTH_REDIRECT_URI, or inject a fake on app.state."
        )
    return client


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
