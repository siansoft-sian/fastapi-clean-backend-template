"""Boundary dependencies: configuration and request-scoped context.

Only delivery-layer concerns belong here (settings, auth context, pagination
parsing). Service providers live in `app/bootstrap/factories.py` — routers
never `Depends(SomeServiceClass)`.
"""

from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]
