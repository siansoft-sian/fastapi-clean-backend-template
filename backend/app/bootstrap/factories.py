"""DI composition root: provider functions consumed by the API boundary.

Services are constructed HERE, with repositories and clients injected through
their constructors. Routers receive them via `Depends(provide_<service>)` —
never `Depends(SomeServiceClass)`, never construction inside handlers.

Shape of a provider (arrives with the first real module):

    def provide_booking_service(request: Request) -> BookingService:
        container: Container = request.app.state.container
        return BookingService(bookings=PostgresBookingRepository(container.db_pool))

Empty by design in M0/M1.
"""
