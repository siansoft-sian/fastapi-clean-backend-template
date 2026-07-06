"""Booking lifecycle. TEMPLATE DEFAULT — # TODO(BA): replace with the real
state machine from the business-analyst stage.

    PENDING  -> APPROVED | CANCELLED
    APPROVED -> CANCELLED | COMPLETED
    CANCELLED / COMPLETED are terminal.
"""

from enum import StrEnum
from typing import Final


class BookingStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


# TODO(BA): template-default transition map.
_ALLOWED_TRANSITIONS: Final[dict[BookingStatus, frozenset[BookingStatus]]] = {
    BookingStatus.PENDING: frozenset({BookingStatus.APPROVED, BookingStatus.CANCELLED}),
    BookingStatus.APPROVED: frozenset({BookingStatus.CANCELLED, BookingStatus.COMPLETED}),
    BookingStatus.CANCELLED: frozenset(),
    BookingStatus.COMPLETED: frozenset(),
}


def allowed_targets(current: BookingStatus) -> frozenset[BookingStatus]:
    return _ALLOWED_TRANSITIONS[current]


def is_allowed_transition(current: BookingStatus, target: BookingStatus) -> bool:
    return target in _ALLOWED_TRANSITIONS[current]
