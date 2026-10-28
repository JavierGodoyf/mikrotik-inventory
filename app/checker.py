from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings, utcnow
from .crypto import decrypt
from .db import SessionLocal
from .evaluate import SnapshotView, evaluate_snapshot, target_line
from .mikrotik import Credentials, collect
from .models import Check, Device
from .upstream import get_latest


def credentials_for(device: Device) -> Credentials:
    settings = get_settings()
    timeout = settings.public_timeout if device.network == "public" else settings.lan_timeout
    return Credentials(
        host=device.host,
        port=device.port,
        username=device.username,
        password=decrypt(device.secret),
        transport=device.transport,
        verify_tls=device.verify_tls,
        timeout=timeout,
    )


def check_device(session: Session, device: Device, run_update_check: bool = False) -> Check:
    started = time.monotonic()
    check = Check(device_id=device.id, started_at=utcnow())

    try:
        snapshot = collect(credentials_for(device), run_update_check=run_update_check)
    except Exception as exc:
        check.ok = False
        check.status = "unreachable"
        check.error = str(exc)
        check.message = f"No se pudo leer el router: {exc}"
        check.duration_ms = int((time.monotonic() - started) * 1000)
        session.add(check)
        session.commit()
        return check

    line = target_line(snapshot.installed_version, snapshot.architecture)
    cached = get_latest(session, line, channels=("stable", "long-term"))
    latest = {channel: row.version for channel, row in cached.items()}

    evaluation = evaluate_snapshot(
        SnapshotView(
            installed_version=snapshot.installed_version,
            architecture=snapshot.architecture,
            free_hdd_kb=snapshot.free_hdd_kb,
            reported_latest=snapshot.latest_reported,
            routerboot_current=snapshot.routerboot_current,
            routerboot_upgrade=snapshot.routerboot_upgrade,
        ),
        preferred_channel=device.channel,
        latest=latest,
    )

    check.ok = True
    check.identity = snapshot.identity
    check.installed_version = snapshot.installed_version
    check.architecture = snapshot.architecture
    check.board_name = snapshot.board_name
    check.platform_name = snapshot.platform_name
    check.channel = snapshot.channel
    check.latest_reported = snapshot.latest_reported
    check.routerboot_current = snapshot.routerboot_current
    check.routerboot_upgrade = snapshot.routerboot_upgrade
    check.firmware_type = snapshot.firmware_type
    check.free_hdd_kb = snapshot.free_hdd_kb
    check.uptime = snapshot.uptime
    check.status = evaluation.status
    check.target_version = evaluation.target_version
    check.target_source = evaluation.target_source
    check.message = evaluation.message
    check.routerboot_outdated = evaluation.routerboot_outdated
    check.raw_json = snapshot.to_json()
    check.duration_ms = int((time.monotonic() - started) * 1000)

    session.add(check)
    session.commit()
    return check


def _check_by_id(device_id: int, run_update_check: bool) -> None:
    with SessionLocal() as session:
        device = session.get(Device, device_id)
        if device is None or not device.enabled:
            return
        try:
            check_device(session, device, run_update_check=run_update_check)
        except Exception:  # una excepción aquí no debe tumbar el resto
            session.rollback()


def check_all(run_update_check: bool = False) -> int:
    settings = get_settings()
    with SessionLocal() as session:
        device_ids = list(session.scalars(select(Device.id).where(Device.enabled.is_(True))).all())
    if not device_ids:
        return 0

    workers = max(1, min(settings.max_concurrency, len(device_ids)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda device_id: _check_by_id(device_id, run_update_check), device_ids))
    return len(device_ids)
