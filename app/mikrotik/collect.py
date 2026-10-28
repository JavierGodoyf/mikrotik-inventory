from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .client import Credentials, connect


@dataclass
class Snapshot:
    identity: str | None = None
    installed_version: str | None = None
    architecture: str | None = None
    board_name: str | None = None
    platform_name: str | None = None
    channel: str | None = None
    latest_reported: str | None = None
    routerboot_current: str | None = None
    routerboot_upgrade: str | None = None
    firmware_type: str | None = None
    free_hdd_kb: int | None = None
    uptime: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, default=str)


def _as_dict(value: Any) -> dict[str, Any]:
    return {k: v for k, v in dict(value).items() if k != ".id"}


def _first(api, *path: str) -> dict[str, Any]:
    for row in api.path(*path):
        return _as_dict(row)
    return {}


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else None


def collect(credentials: Credentials, run_update_check: bool = False) -> Snapshot:
    """Lee el estado del router. Solo ejecuta comandos de lectura.

    `run_update_check` lanza /system/package/update/check-for-updates, que
    puede requerir más permisos que 'read'; está desactivado por defecto.
    """
    api = connect(credentials)
    try:
        resource = _first(api, "system", "resource")
        update = _first(api, "system", "package", "update")

        if run_update_check:
            try:
                tuple(api.path("system", "package", "update")("check-for-updates"))
                update = _first(api, "system", "package", "update")
            except Exception:
                # Sin permisos suficientes: seguimos con lo que ya teníamos.
                pass

        try:
            routerboard = _first(api, "system", "routerboard")
        except Exception:
            routerboard = {}

        try:
            identity = _first(api, "system", "identity").get("name")
        except Exception:
            identity = None

        snapshot = Snapshot(
            identity=identity,
            installed_version=resource.get("version"),
            architecture=resource.get("architecture-name"),
            board_name=resource.get("board-name"),
            platform_name=resource.get("platform"),
            channel=update.get("channel"),
            latest_reported=update.get("latest-version"),
            routerboot_current=routerboard.get("current-firmware"),
            routerboot_upgrade=routerboard.get("upgrade-firmware"),
            firmware_type=routerboard.get("firmware-type"),
            free_hdd_kb=_int(resource.get("free-hdd-space")),
            uptime=resource.get("uptime"),
            raw={"resource": resource, "update": update, "routerboard": routerboard},
        )
        return snapshot
    finally:
        try:
            api.close()
        except Exception:
            pass
