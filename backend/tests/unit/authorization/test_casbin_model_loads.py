"""The authored model + policy files exist and initialize a Casbin enforcer.

Also pins the request_definition — the coordination point between the
casbin-policy-engineer model and AuthorizationService's enforce() call shape.
"""

from pathlib import Path

import casbin

AUTHZ_DIR = Path(__file__).resolve().parents[3] / "app" / "authorization"
MODEL_PATH = AUTHZ_DIR / "casbin_model.conf"
POLICY_PATH = AUTHZ_DIR / "policy.csv"


def test_model_and_policy_files_exist() -> None:
    assert MODEL_PATH.is_file()
    assert POLICY_PATH.is_file()


def test_enforcer_initializes_with_model_and_policy() -> None:
    enforcer = casbin.Enforcer(str(MODEL_PATH), str(POLICY_PATH))
    assert len(enforcer.get_policy()) >= 6  # the five rules (+ the deny row)


def test_request_definition_matches_integration_contract() -> None:
    """enforce(sub, dom, obj, act) — AuthorizationService depends on this order."""
    enforcer = casbin.Enforcer(str(MODEL_PATH), str(POLICY_PATH))
    tokens = enforcer.model["r"]["r"].tokens
    assert tokens == ["r_sub", "r_dom", "r_obj", "r_act"]
