"""Bookings — the template's REFERENCE module. Copy this shape for new modules.

    api/             thin router + boundary schemas (the ONLY FastAPI-aware layer)
    application/     commands/queries/DTOs + use cases (ports + domain only)
    domain/          pure entities, lifecycle, policy, events, errors
    ports/           the Protocols use cases depend on
    infrastructure/  adapters: asyncpg repo (the only engine-aware code),
                     authorization + outbox adapters, in-memory fake
    tests/           module-local tests (fast: fakes only)

Request flow: router -> use case -> [AuthorizationPort.enforce -> domain
policy -> BookingRepositoryProtocol -> OutboxPort.emit] -> envelope.

Business rules here are TEMPLATE DEFAULTS marked # TODO(BA) — the real rules
come from the business-analyst stage, not this scaffold.
"""
