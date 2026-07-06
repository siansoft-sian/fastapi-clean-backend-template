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
