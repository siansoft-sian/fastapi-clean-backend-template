"""Uvicorn runner ONLY. The application factory lives in `app/app.py` — never merge them."""

import uvicorn

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.app:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=settings.app_debug,
    )


if __name__ == "__main__":
    main()
