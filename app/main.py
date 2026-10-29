from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import scheduler
from .checker import check_all, check_device
from .config import APP_DIR, get_settings, to_local
from .crypto import encrypt
from .db import get_session, init_db
from .evaluate import STATUS_CSS, STATUS_LABELS, STATUS_ORDER
from .mikrotik.discovery import DiscoveryError, discover
from .models import Check, Device, LatestCache
from .watchguard import service as watchguard
from .watchguard.config import get_wg_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="MikroTik Inventory", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
templates.env.filters["local"] = lambda value: (
    to_local(value).strftime("%Y-%m-%d %H:%M") if value else "—"
)
templates.env.globals.update(
    LABELS=STATUS_LABELS, CSS=STATUS_CSS, ORDER=STATUS_ORDER, WG_ENABLED=get_wg_settings().active
)


# --------------------------------------------------------------------------- helpers


def _last_check(session: Session, device_id: int) -> Check | None:
    return session.scalar(
        select(Check).where(Check.device_id == device_id).order_by(Check.started_at.desc()).limit(1)
    )


def _dashboard_rows(session: Session) -> list[dict]:
    devices = session.scalars(select(Device).order_by(Device.name)).all()
    return [{"device": device, "check": _last_check(session, device.id)} for device in devices]


def _counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = row["check"].status if row["check"] else "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _redirect(url: str, message: str) -> RedirectResponse:
    separator = "&" if "?" in url else "?"
    return RedirectResponse(f"{url}{separator}msg={quote(message)}", status_code=303)


def _int(form, key: str, default: int) -> int:
    raw = form.get(key)
    if raw in (None, ""):
        return default
    try:
        return int(str(raw))
    except ValueError:
        return default


def _device_from_form(form, device: Device | None = None) -> Device:
    target = device or Device()
    target.name = (form.get("name") or "").strip()
    target.host = (form.get("host") or "").strip()
    target.transport = form.get("transport") or "api"
    target.port = _int(form, "port", 8729 if target.transport == "api_ssl" else 8728)
    if device is None and target.transport == "api_ssl" and target.port == 8728:
        target.port = 8729
    target.username = (form.get("username") or "panel").strip()
    target.network = form.get("network") or "lan"
    target.channel = form.get("channel") or "stable"
    target.site = (form.get("site") or "").strip()
    target.tags = (form.get("tags") or "").strip()
    target.notes = (form.get("notes") or "").strip()
    target.enabled = form.get("enabled") is not None
    target.verify_tls = form.get("verify_tls") is not None

    password = form.get("password") or ""
    if password:
        target.secret = encrypt(password)
    elif device is None:
        target.secret = encrypt("")
    return target


# --------------------------------------------------------------------------- HTML


@app.get("/")
def index(request: Request, session: Session = Depends(get_session)):
    rows = _dashboard_rows(session)
    counts = _counts(rows)
    settings = get_settings()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "rows": rows,
            "counts": counts,
            "total": len(rows),
            "next_run": scheduler.next_run(),
            "interval_hours": settings.check_interval_hours,
        },
    )


@app.get("/devices/new")
def device_new(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="device_form.html",
        context={"device": None, "prefill": request.query_params},
    )


@app.post("/devices")
async def device_create(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    if not (form.get("password") or "").strip():
        return _redirect("/devices/new", "La contraseña es obligatoria.")
    device = _device_from_form(form)
    if not device.name or not device.host:
        return _redirect("/devices/new", "Nombre y host son obligatorios.")
    session.add(device)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return _redirect("/devices/new", f"Ya existe un equipo llamado '{device.name}'.")
    return _redirect(f"/devices/{device.id}", "Equipo creado.")


@app.get("/devices/{device_id}")
def device_detail(device_id: int, request: Request, session: Session = Depends(get_session)):
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    checks = session.scalars(
        select(Check)
        .where(Check.device_id == device_id)
        .order_by(Check.started_at.desc())
        .limit(50)
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="device.html",
        context={"device": device, "checks": checks, "check": checks[0] if checks else None},
    )


@app.get("/devices/{device_id}/edit")
def device_edit(device_id: int, request: Request, session: Session = Depends(get_session)):
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    return templates.TemplateResponse(
        request=request,
        name="device_form.html",
        context={"device": device, "prefill": {}},
    )


@app.post("/devices/{device_id}/edit")
async def device_update(device_id: int, request: Request, session: Session = Depends(get_session)):
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    form = await request.form()
    _device_from_form(form, device)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return _redirect(f"/devices/{device_id}/edit", "Ese nombre ya está en uso.")
    return _redirect(f"/devices/{device_id}", "Equipo actualizado.")


@app.post("/devices/{device_id}/delete")
def device_delete(device_id: int, session: Session = Depends(get_session)):
    device = session.get(Device, device_id)
    if device is not None:
        session.delete(device)
        session.commit()
    return _redirect("/", "Equipo eliminado.")


@app.post("/devices/{device_id}/check")
def device_check(device_id: int, session: Session = Depends(get_session)):
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    check = check_device(session, device)
    if check.status == "unreachable":
        return _redirect(f"/devices/{device_id}", f"Sin conexión: {check.error or ''}")
    return _redirect(f"/devices/{device_id}", "Comprobación completada.")


@app.post("/check-all")
def check_everything(background: BackgroundTasks):
    background.add_task(check_all)
    return _redirect("/", "Comprobación de todos los equipos en marcha.")


@app.get("/discover")
def discover_page(request: Request):
    error = None
    devices: list[dict] = []
    try:
        devices = discover(timeout=3.0)
    except DiscoveryError as exc:
        error = str(exc)
    except Exception as exc:  # pragma: no cover
        error = f"Fallo inesperado: {exc}"
    known = set()
    return templates.TemplateResponse(
        request=request,
        name="discover.html",
        context={"devices": devices, "error": error},
    )


# --------------------------------------------------------------------------- JSON / export


@app.get("/api/devices")
def api_devices(session: Session = Depends(get_session)):
    rows = _dashboard_rows(session)
    payload = []
    for row in rows:
        device, check = row["device"], row["check"]
        payload.append(
            {
                "id": device.id,
                "name": device.name,
                "host": device.host,
                "port": device.port,
                "transport": device.transport,
                "network": device.network,
                "channel": device.channel,
                "enabled": device.enabled,
                "check": None
                if check is None
                else {
                    "started_at": check.started_at.isoformat(),
                    "ok": check.ok,
                    "status": check.status,
                    "installed_version": check.installed_version,
                    "target_version": check.target_version,
                    "target_source": check.target_source,
                    "architecture": check.architecture,
                    "board_name": check.board_name,
                    "routerboot_current": check.routerboot_current,
                    "routerboot_upgrade": check.routerboot_upgrade,
                    "routerboot_outdated": check.routerboot_outdated,
                    "message": check.message,
                    "error": check.error,
                },
            }
        )
    return payload


@app.get("/report.csv")
def report_csv(session: Session = Depends(get_session)):
    rows = _dashboard_rows(session)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "equipo",
            "host",
            "red",
            "canal",
            "modelo",
            "arquitectura",
            "instalada",
            "objetivo",
            "routerboot_actual",
            "routerboot_upgrade",
            "estado",
            "detalle",
            "ultimo_chequeo",
        ]
    )
    for row in rows:
        device, check = row["device"], row["check"]
        writer.writerow(
            [
                device.name,
                f"{device.host}:{device.port}",
                device.network,
                device.channel,
                check.board_name if check else "",
                check.architecture if check else "",
                check.installed_version if check else "",
                check.target_version if check else "",
                check.routerboot_current if check else "",
                check.routerboot_upgrade if check else "",
                STATUS_LABELS.get(check.status, check.status) if check else "Sin datos",
                (check.message or "") if check else "",
                to_local(check.started_at).strftime("%Y-%m-%d %H:%M") if check else "",
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="mikrotik-inventory.csv"'},
    )


@app.get("/healthz")
def healthz(session: Session = Depends(get_session)):
    counts = _counts(_dashboard_rows(session))
    cached = {
        f"{row.line}/{row.channel}": row.version
        for row in session.scalars(select(LatestCache)).all()
    }
    health = {"status": "ok", "devices": sum(counts.values()), "counts": counts, "latest": cached}
    if get_wg_settings().active:
        last, good = watchguard.last_runs(session)
        health["watchguard"] = {
            "devices": good.total if good else 0,
            "critical": good.critical if good else 0,
            "last_run": last.started_at.isoformat() if last else None,
            "last_ok": bool(last and last.ok),
        }
    return health


# --------------------------------------------------------------------------- WatchGuard


def _require_watchguard() -> None:
    if not get_wg_settings().active:
        raise HTTPException(status_code=404, detail="WatchGuard no está configurado (variables WG_* en .env)")


@app.get("/watchguard")
def watchguard_page(request: Request):
    _require_watchguard()
    return templates.TemplateResponse(
        request=request,
        name="watchguard.html",
        context={
            "next_run": scheduler.next_run("wg-refresh"),
            "interval_hours": get_wg_settings().interval_hours,
        },
    )


@app.get("/api/watchguard")
def api_watchguard(background: BackgroundTasks, session: Session = Depends(get_session)):
    _require_watchguard()
    payload = watchguard.status_payload(session)
    # Primera visita sin ninguna lectura guardada: se lanza una sin esperar al scheduler.
    if payload["lastAttemptAt"] is None and not payload["running"]:
        background.add_task(watchguard.refresh)
        payload["running"] = True
    return payload


@app.post("/watchguard/refresh")
def watchguard_refresh(background: BackgroundTasks):
    _require_watchguard()
    if watchguard.is_running():
        return _redirect("/watchguard", "Ya hay una lectura de WatchGuard Cloud en marcha.")
    background.add_task(watchguard.refresh)
    return _redirect("/watchguard", "Lectura de WatchGuard Cloud en marcha.")
