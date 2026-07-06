"""The five locked authorization rules, via AuthorizationService.enforce()
against the REAL model + policy files — plus cross-tenant, has_scope, and
compute_scopes behavior. enforce() raises ForbiddenError; it never returns.
"""

from dataclasses import dataclass

import pytest

from app.authorization import permission_actions as pa
from app.authorization.authorization_service import (
    CROSS_TENANT_REASON,
    AuthorizationService,
)
from app.authorization.casbin_enforcer import CasbinEnforcer
from app.authorization.resource_context import ResourceContext
from app.core.errors.core_errors import ForbiddenError

T1, T2 = "tenant-1", "tenant-2"


@pytest.fixture(scope="module")
def service() -> AuthorizationService:
    enforcer = CasbinEnforcer(
        model_path="app/authorization/casbin_model.conf",
        policy_path="app/authorization/policy.csv",
    )
    return AuthorizationService(enforcer)


def ctx(
    *,
    roles: frozenset[str],
    action: str,
    resource_type: str,
    actor: str = "actor-1",
    owner: str | None = None,
    assigned: frozenset[str] = frozenset(),
    resource_tenant: str | None = T1,
) -> ResourceContext:
    return ResourceContext(
        actor_user_id=actor,
        tenant_id=T1,
        roles=roles,
        action=action,
        resource_type=resource_type,
        resource_id="res-1",
        resource_owner_id=owner,
        assigned_user_ids=assigned,
        resource_tenant_id=resource_tenant,
    )


# --- rule 1: admin manages all bookings in tenant ---


@pytest.mark.parametrize("action", [pa.CREATE, pa.READ, pa.UPDATE, pa.APPROVE, pa.CANCEL])
def test_rule1_admin_any_booking_action(service: AuthorizationService, action: str) -> None:
    service.enforce(ctx(roles=frozenset({"admin"}), action=action, resource_type=pa.BOOKING))


# --- rule 2: manager approves in own tenant only ---


def test_rule2_manager_approves_in_tenant(service: AuthorizationService) -> None:
    service.enforce(ctx(roles=frozenset({"manager"}), action=pa.APPROVE, resource_type=pa.BOOKING))


def test_rule2_manager_cross_tenant_denied(service: AuthorizationService) -> None:
    with pytest.raises(ForbiddenError) as exc_info:
        service.enforce(
            ctx(
                roles=frozenset({"manager"}),
                action=pa.APPROVE,
                resource_type=pa.BOOKING,
                resource_tenant=T2,
            )
        )
    assert exc_info.value.details["reason"] == CROSS_TENANT_REASON


def test_rule2_manager_cannot_cancel(service: AuthorizationService) -> None:
    with pytest.raises(ForbiddenError):
        service.enforce(
            ctx(roles=frozenset({"manager"}), action=pa.CANCEL, resource_type=pa.BOOKING)
        )


# --- rule 3: staff read only assigned events ---


def test_rule3_staff_reads_assigned_event(service: AuthorizationService) -> None:
    service.enforce(
        ctx(
            roles=frozenset({"staff"}),
            action=pa.READ,
            resource_type=pa.EVENT,
            actor="staff-7",
            assigned=frozenset({"staff-7", "staff-9"}),
        )
    )


def test_rule3_staff_unassigned_event_denied(service: AuthorizationService) -> None:
    with pytest.raises(ForbiddenError):
        service.enforce(
            ctx(
                roles=frozenset({"staff"}),
                action=pa.READ,
                resource_type=pa.EVENT,
                actor="staff-7",
                assigned=frozenset({"staff-9"}),
            )
        )


# --- rule 4: owner updates own profile ---


def test_rule4_owner_updates_own_profile(service: AuthorizationService) -> None:
    service.enforce(
        ctx(
            roles=frozenset({"owner"}),
            action=pa.UPDATE,
            resource_type=pa.PROFILE,
            actor="user-4",
            owner="user-4",
        )
    )


def test_rule4_owner_cannot_update_other_profile(service: AuthorizationService) -> None:
    with pytest.raises(ForbiddenError):
        service.enforce(
            ctx(
                roles=frozenset({"owner"}),
                action=pa.UPDATE,
                resource_type=pa.PROFILE,
                actor="user-4",
                owner="user-5",
            )
        )


# --- rule 5: refund requires finance (deny-override) ---


def test_rule5_finance_refund_allowed(service: AuthorizationService) -> None:
    service.enforce(ctx(roles=frozenset({"finance"}), action=pa.REFUND, resource_type=pa.PAYMENT))


def test_rule5_admin_without_finance_denied(service: AuthorizationService) -> None:
    # Even a role with broad grants loses to the deny rule without `finance`.
    with pytest.raises(ForbiddenError):
        service.enforce(
            ctx(
                roles=frozenset({"admin", "manager"}),
                action=pa.REFUND,
                resource_type=pa.PAYMENT,
            )
        )


def test_rule5_admin_plus_finance_allowed(service: AuthorizationService) -> None:
    service.enforce(
        ctx(roles=frozenset({"admin", "finance"}), action=pa.REFUND, resource_type=pa.PAYMENT)
    )


# --- structural guarantees ---


def test_no_roles_is_denied(service: AuthorizationService) -> None:
    with pytest.raises(ForbiddenError):
        service.enforce(ctx(roles=frozenset(), action=pa.READ, resource_type=pa.BOOKING))


def test_enforce_returns_none_on_allow(service: AuthorizationService) -> None:
    result = service.enforce(
        ctx(roles=frozenset({"admin"}), action=pa.READ, resource_type=pa.BOOKING)
    )
    assert result is None  # never a bool a caller could forget to check


# --- coarse layer: has_scope + compute_scopes ---


@dataclass(frozen=True)
class StubPrincipal:
    scopes: frozenset[str]


def test_has_scope_checks_membership(service: AuthorizationService) -> None:
    principal = StubPrincipal(scopes=frozenset({"booking.approve"}))
    assert service.has_scope(principal, "booking.approve") is True
    assert service.has_scope(principal, "payment.refund") is False


def test_compute_scopes_expands_wildcards_from_policy(service: AuthorizationService) -> None:
    admin_scopes = service.compute_scopes(frozenset({"admin"}), T1)
    # admin: booking.* expands over the booking action registry
    assert admin_scopes == {
        pa.scope_for(pa.BOOKING, action) for action in pa.ACTIONS_BY_RESOURCE[pa.BOOKING]
    }

    manager_scopes = service.compute_scopes(frozenset({"manager"}), T1)
    assert manager_scopes == {"booking.approve"}

    finance_scopes = service.compute_scopes(frozenset({"finance"}), T1)
    assert finance_scopes == {"payment.refund"}

    # staff/owner grants are instance-conditional but still yield coarse scopes.
    assert service.compute_scopes(frozenset({"staff"}), T1) == {"event.read"}
    assert service.compute_scopes(frozenset({"owner"}), T1) == {"profile.update"}

    assert service.compute_scopes(frozenset(), T1) == frozenset()
