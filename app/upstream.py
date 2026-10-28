from __future__ import annotations

from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings, utcnow
from .models import LatestCache

BASE_URL = "https://upgrade.mikrotik.com/routeros/"

# Los endpoints "NEWESTx" son los antiguos y devuelven versiones congeladas;
# los que usa RouterOS hoy son los "NEWESTa" (verificado en oct-2026).
ENDPOINTS: dict[tuple[str, str], str] = {
    ("7", "stable"): "NEWESTa7.stable",
    ("7", "long-term"): "NEWESTa7.long-term",
    ("7", "testing"): "NEWESTa7.testing",
    ("6", "stable"): "NEWESTa6.stable",
    ("6", "long-term"): "NEWESTa6.long-term",
}

CHANNELS = ("stable", "long-term")


class UpstreamError(RuntimeError):
    pass


def fetch_latest(channel: str, line: str, timeout: float | None = None) -> tuple[str, datetime | None]:
    """Devuelve (versión, fecha de publicación) según MikroTik."""
    key = (line, channel)
    if key not in ENDPOINTS:
        raise UpstreamError(f"Canal no soportado: {line}/{channel}")

    settings = get_settings()
    url = BASE_URL + ENDPOINTS[key]
    try:
        response = httpx.get(
            url,
            timeout=timeout or settings.upstream_timeout,
            follow_redirects=True,
            headers={"User-Agent": "mikrotik-inventory/0.1"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise UpstreamError(f"No se pudo consultar {url}: {exc}") from exc

    parts = response.text.split()
    if not parts or parts[0] in {"0.00", "0", ""}:
        raise UpstreamError(f"MikroTik no publica versión para {line}/{channel}")

    version = parts[0].strip()
    released: datetime | None = None
    if len(parts) > 1 and parts[1].isdigit():
        released = datetime.fromtimestamp(int(parts[1]), tz=timezone.utc).replace(tzinfo=None)
    return version, released


def get_latest(
    session: Session,
    line: str,
    channels: tuple[str, ...] = CHANNELS,
    max_age_hours: float | None = None,
) -> dict[str, LatestCache]:
    """Versiones por canal, con caché en SQLite y fallback a la última conocida."""
    settings = get_settings()
    max_age = (max_age_hours if max_age_hours is not None else settings.upstream_cache_hours) * 3600
    now = utcnow()
    result: dict[str, LatestCache] = {}

    for channel in channels:
        row = session.scalar(
            select(LatestCache).where(LatestCache.line == line, LatestCache.channel == channel)
        )
        fresh = row is not None and (now - row.fetched_at).total_seconds() < max_age
        if fresh:
            result[channel] = row
            continue

        try:
            version, released = fetch_latest(channel, line)
        except UpstreamError:
            if row is not None:  # mejor una versión vieja que ninguna
                result[channel] = row
            continue

        if row is None:
            row = LatestCache(line=line, channel=channel, version=version, released_at=released)
            session.add(row)
        else:
            row.version = version
            row.released_at = released
            row.fetched_at = now
        session.flush()
        result[channel] = row

    return result
