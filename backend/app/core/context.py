"""Request-scoped context propagated via contextvars — never module globals.

Set by `RequestContextMiddleware`; read by envelope helpers, logging, and the
exception boundary. Auth and tenant contextvars arrive with their milestones.
"""

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Current request id, or None outside a request scope."""
    return request_id_var.get()
