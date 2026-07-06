"""Sentinels distinguishing "not provided" from "explicitly None".

Use `UNSET` for optional update fields (PATCH semantics) and `MISSING` for
lookups that must separate "absent" from "present but None". Enum members are
typing-friendly: `str | None | Literal[Sentinel.UNSET]`.
"""

from enum import Enum
from typing import Final, Literal


class Sentinel(Enum):
    UNSET = "UNSET"
    MISSING = "MISSING"

    def __repr__(self) -> str:
        return f"<{self.name}>"

    def __bool__(self) -> Literal[False]:
        return False


UNSET: Final = Sentinel.UNSET
MISSING: Final = Sentinel.MISSING
