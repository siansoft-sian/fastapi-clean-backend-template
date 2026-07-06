"""Bookings router — THIN by rule.

Each handler: parse -> Depends[auth+scope, csrf, rate_limit] -> one use case
-> envelope. No SQL, no business rules, no authz logic, no Casbin/Redis calls
here; the fine-grained authorization runs INSIDE the use case (Layer 2,
authoritative).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.auth import scopes
from app.auth.auth_context import AuthContext
from app.auth.dependencies import require_scope, verify_csrf
from app.bootstrap.factories import (
    provide_approve_booking_use_case,
    provide_cancel_booking_use_case,
    provide_create_booking_use_case,
    provide_get_booking_use_case,
)
from app.core.responses import api_success
from app.modules.bookings.api.schemas import (
    BookingResponse,
    CancelBookingRequest,
    CreateBookingRequest,
)
from app.modules.bookings.application.commands import (
    ApproveBookingCommand,
    CancelBookingCommand,
    CreateBookingCommand,
)
from app.modules.bookings.application.queries import GetBookingQuery
from app.modules.bookings.application.use_cases.approve_booking import ApproveBookingUseCase
from app.modules.bookings.application.use_cases.cancel_booking import CancelBookingUseCase
from app.modules.bookings.application.use_cases.create_booking import CreateBookingUseCase
from app.modules.bookings.application.use_cases.get_booking import GetBookingUseCase
from app.rate_limiting.dependency import rate_limit

router = APIRouter(prefix="/bookings", tags=["bookings"])

# require_scope() chains get_current_principal, so the principal parameter
# below IS the authenticated + coarse-scope-checked actor.
CreatorDep = Annotated[AuthContext, Depends(require_scope(scopes.BOOKING_CREATE))]
ReaderDep = Annotated[AuthContext, Depends(require_scope(scopes.BOOKING_READ))]
ApproverDep = Annotated[AuthContext, Depends(require_scope(scopes.BOOKING_APPROVE))]
CancellerDep = Annotated[AuthContext, Depends(require_scope(scopes.BOOKING_CANCEL))]


@router.post(
    "",
    status_code=201,
    dependencies=[Depends(verify_csrf), Depends(rate_limit("booking.create"))],
)
async def create_booking(
    body: CreateBookingRequest,
    principal: CreatorDep,
    use_case: Annotated[CreateBookingUseCase, Depends(provide_create_booking_use_case)],
) -> dict[str, Any]:
    # TODO(M7-idempotency): this route is the Idempotency-Key target.
    command = CreateBookingCommand(
        reference=body.reference, resource_id=body.resource_id, scheduled_at=body.scheduled_at
    )
    booking = await use_case.execute(command, principal)
    return api_success(BookingResponse.from_dto(booking).model_dump(mode="json"))


@router.get(
    "/{booking_id}",
    dependencies=[Depends(rate_limit("events.read"))],
)
async def get_booking(
    booking_id: str,
    principal: ReaderDep,
    use_case: Annotated[GetBookingUseCase, Depends(provide_get_booking_use_case)],
) -> dict[str, Any]:
    booking = await use_case.execute(GetBookingQuery(booking_id=booking_id), principal)
    return api_success(BookingResponse.from_dto(booking).model_dump(mode="json"))


@router.post(
    "/{booking_id}/approve",
    dependencies=[Depends(verify_csrf), Depends(rate_limit("booking.approve"))],
)
async def approve_booking(
    booking_id: str,
    principal: ApproverDep,
    use_case: Annotated[ApproveBookingUseCase, Depends(provide_approve_booking_use_case)],
) -> dict[str, Any]:
    booking = await use_case.execute(ApproveBookingCommand(booking_id=booking_id), principal)
    return api_success(BookingResponse.from_dto(booking).model_dump(mode="json"))


@router.post(
    "/{booking_id}/cancel",
    dependencies=[Depends(verify_csrf), Depends(rate_limit("booking.create"))],
)
async def cancel_booking(
    booking_id: str,
    principal: CancellerDep,
    use_case: Annotated[CancelBookingUseCase, Depends(provide_cancel_booking_use_case)],
    body: CancelBookingRequest | None = None,
) -> dict[str, Any]:
    command = CancelBookingCommand(booking_id=booking_id, reason=body.reason if body else None)
    booking = await use_case.execute(command, principal)
    return api_success(BookingResponse.from_dto(booking).model_dump(mode="json"))
