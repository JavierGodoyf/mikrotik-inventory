from __future__ import annotations

import uvicorn

from .config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        workers=1,  # el scheduler vive en el proceso: nunca más de un worker
        log_level="warning",
    )


if __name__ == "__main__":
    main()
