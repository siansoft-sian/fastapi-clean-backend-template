"""Health endpoint payloads — the `data` part of the success envelope."""

from typing import Literal

from pydantic import BaseModel, Field


class LivenessData(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessData(BaseModel):
    """`degraded` means some dependencies are intentionally disabled — still 200."""

    status: Literal["ok", "degraded"]
    components: dict[str, str] = Field(default_factory=dict)


class DeepHealthData(ReadinessData):
    """Readiness plus extended probes (pool stats, migrations — arrive in M2+)."""

    checks: dict[str, str] = Field(default_factory=dict)
