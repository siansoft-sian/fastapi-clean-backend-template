"""Health endpoint payloads — the `data` part of the success envelope."""

from typing import Literal

from pydantic import BaseModel, Field


class LivenessData(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessData(BaseModel):
    """Component states: ok | disabled | unknown | error.

    Overall status: `error` (HTTP 503) when any enabled component fails;
    `ok` when at least one component is verified and none is unverifiable;
    `degraded` (still 200) when dependencies are intentionally disabled.
    """

    status: Literal["ok", "degraded", "error"]
    components: dict[str, str] = Field(default_factory=dict)


class DeepHealthData(ReadinessData):
    """Readiness plus extended probes (pool stats, migrations — arrive later)."""

    checks: dict[str, str] = Field(default_factory=dict)
