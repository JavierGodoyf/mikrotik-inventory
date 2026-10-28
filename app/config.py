from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import os

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(os.environ.get("MTIK_BASE_DIR") or Path.cwd())
APP_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_prefix="MTIK_",
        extra="ignore",
    )

    db_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'devices.db').as_posix()}"
    key_file: Path = BASE_DIR / "data" / "secret.key"

    check_interval_hours: float = 6
    lan_timeout: float = 8
    public_timeout: float = 15
    upstream_timeout: float = 10
    upstream_cache_hours: float = 6
    max_concurrency: int = 8

    scheduler_enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.key_file).parent.mkdir(parents=True, exist_ok=True)
    return settings


def utcnow() -> datetime:
    """Naive UTC timestamp, que es lo que SQLite guarda de forma fiable."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_local(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).astimezone()
