from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from threading import Lock

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import utcnow
from ..db import SessionLocal
from ..models import WgRun
from . import psirt
from .client import WatchGuardClient
from .config import get_wg_settings
from .summary import demo_data, summarize

log = logging.getLogger(__name__)

KEEP_RUNS = 200  # histórico de lecturas que se conserva en SQLite

_refresh_lock = Lock()  # una sola lectura a la vez (scheduler, botón o primera visita)

# Avisos de seguridad de WatchGuard, con caché propia en memoria (cambian pocas veces al día).
_psirt = {"at": 0.0, "advisories": None, "error": None}


def _iso(value: datetime | float | None) -> str | None:
    if not value:
        return None
    if isinstance(value, float):
        value = datetime.fromtimestamp(value, timezone.utc)
    else:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def get_advisories() -> dict:
    settings = get_wg_settings()
    if not settings.psirt:
        return _psirt
    if _psirt["advisories"] and time.time() - _psirt["at"] < settings.psirt_cache_hours * 3600:
        return _psirt
    try:
        _psirt.update(advisories=psirt.fetch_advisories(), at=time.time(), error=None)
    except Exception as exc:
        # Si falla, se sigue usando la última lista buena (si la hay).
        log.warning("No se pudieron leer los avisos de WatchGuard: %s", exc)
        _psirt["error"] = str(exc)
    return _psirt


def is_running() -> bool:
    return _refresh_lock.locked()


def refresh() -> WgRun | None:
    """Lee WatchGuard Cloud y los avisos, y guarda el resultado. None si ya había una lectura en marcha."""
    settings = get_wg_settings()
    if not settings.active or not _refresh_lock.acquire(blocking=False):
        return None
    try:
        started = time.monotonic()
        run = WgRun(started_at=utcnow())
        try:
            if settings.demo:
                raw = demo_data()
            else:
                with WatchGuardClient(settings) as client:
                    raw = client.collect()
            info = get_advisories()
            data = summarize(raw, info["advisories"], settings)
            data["psirt"] = {
                "enabled": settings.psirt,
                "fetchedAt": _iso(info["at"]),
                "advisories": len(info["advisories"] or []),
                "error": info["error"],
            }
            run.ok = True
            run.total, run.updated, run.outdated, run.critical = (
                data["totals"][k] for k in ("total", "updated", "outdated", "critical")
            )
            run.payload_json = json.dumps(data, ensure_ascii=False)
        except Exception as exc:  # se guarda el fallo para mostrarlo en el panel
            log.warning("No se pudo leer WatchGuard Cloud: %s", exc)
            run.ok = False
            run.error = str(exc)[:2000]
        run.duration_ms = int((time.monotonic() - started) * 1000)

        with SessionLocal() as session:
            session.add(run)
            session.flush()
            keep = select(WgRun.id).order_by(WgRun.id.desc()).limit(KEEP_RUNS)
            session.execute(delete(WgRun).where(WgRun.id.not_in(keep)))
            session.commit()
        return run
    finally:
        _refresh_lock.release()


def last_runs(session: Session) -> tuple[WgRun | None, WgRun | None]:
    """(última lectura, última lectura correcta)."""
    last = session.scalar(select(WgRun).order_by(WgRun.id.desc()).limit(1))
    if last is None or last.ok:
        return last, last
    return last, session.scalar(select(WgRun).where(WgRun.ok.is_(True)).order_by(WgRun.id.desc()).limit(1))


def status_payload(session: Session) -> dict:
    """JSON de /api/watchguard: el último resumen bueno, y aviso si la última lectura falló."""
    last, good = last_runs(session)
    payload: dict = json.loads(good.payload_json) if good else {}
    payload.update(
        running=is_running(),
        checkedAt=_iso(good.started_at) if good else None,
        stale=bool(last and not last.ok),
        lastError=last.error if last and not last.ok else None,
        lastAttemptAt=_iso(last.started_at) if last else None,
    )
    return payload
