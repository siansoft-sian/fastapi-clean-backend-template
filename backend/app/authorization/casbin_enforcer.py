"""Casbin enforcer wrapper. Pure: no FastAPI; reads only LOCAL files.

Construction loads the model + policy from disk — call it from
container.startup() or the DI factory, never at import time. All access is
serialized with a lock so `reload()` (policy refresh) can swap the underlying
enforcer safely; decisions are in-memory and take microseconds.

Request shape (coordination point — see casbin_model.conf):

    enforce(sub, dom, obj, act)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import casbin

from app.core.config import Settings

# authorization/ -> app/ -> backend/: makes the settings' relative default
# paths work regardless of the process working directory.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _resolve(path_value: str) -> str:
    path = Path(path_value)
    return str(path if path.is_absolute() else _BACKEND_ROOT / path)


@dataclass(frozen=True)
class EnforcerSubject:
    """`r.sub` in the matcher: the actor and their tenant-resolved roles."""

    id: str
    roles: tuple[str, ...]


@dataclass(frozen=True)
class EnforcerResource:
    """`r.obj` in the matcher. Empty string means "attribute not applicable"."""

    type: str
    owner_id: str = ""
    assigned: tuple[str, ...] = ()
    tenant: str = ""


class CasbinEnforcer:
    def __init__(self, *, model_path: str, policy_path: str) -> None:
        self._model_path = _resolve(model_path)
        self._policy_path = _resolve(policy_path)
        self._lock = threading.Lock()
        self._enforcer = casbin.Enforcer(self._model_path, self._policy_path)

    @classmethod
    def from_settings(cls, settings: Settings) -> CasbinEnforcer:
        return cls(
            model_path=settings.casbin_model_path,
            policy_path=settings.casbin_policy_path,
        )

    def enforce(
        self,
        subject: EnforcerSubject,
        domain: str,
        resource: EnforcerResource,
        action: str,
    ) -> bool:
        with self._lock:
            return bool(self._enforcer.enforce(subject, domain, resource, action))

    def reload(self) -> None:
        """Rebuild from the files (policy refresh); serialized against enforce()."""
        with self._lock:
            self._enforcer = casbin.Enforcer(self._model_path, self._policy_path)

    def policy_rules(self) -> list[list[str]]:
        """The raw p-rules [role, obj_type, act, cond, eft] — used by compute_scopes."""
        with self._lock:
            return [list(rule) for rule in self._enforcer.get_policy()]
