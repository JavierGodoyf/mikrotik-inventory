from __future__ import annotations

import re

from . import psirt
from .config import WatchGuardSettings
from .psirt import SEVERITIES, branch_of, compare_versions

STATUS_ORDER = {"critical": 0, "outdated": 1, "updated": 2}


def manual_latest(settings: WatchGuardSettings) -> dict[str, str]:
    """Versiones forzadas en WG_LATEST_FIREWARE, asignadas a su rama."""
    latest: dict[str, str] = {}
    for version in filter(None, (v.strip() for v in settings.latest_fireware.split(","))):
        latest["T15/T35" if re.match(r"12\.5\.", version) else branch_of("", version)] = version
    return latest


def summarize(raw: dict, advisories: list[dict] | None, settings: WatchGuardSettings) -> dict:
    """Cruza los equipos con los avisos: estado de cada uno, última versión por rama y totales."""
    devices, errors = raw["devices"], raw["errors"]
    advisories = advisories or []
    forced = manual_latest(settings)
    rank = SEVERITIES.index

    # Última versión por rama: manual (.env) > avisos de WatchGuard > la más alta vista en el parque.
    from_psirt = psirt.latest_by_branch(advisories)
    observed: dict[str, str] = {}
    for d in devices:
        if not d.get("version"):
            continue
        branch = branch_of(d.get("short_model_name"), d["version"])
        if branch not in observed or compare_versions(d["version"], observed[branch]) > 0:
            observed[branch] = d["version"]
    latest: dict[str, dict] = {}
    for branch in {*observed, *from_psirt, *forced}:
        if branch in forced:
            latest[branch] = {"version": forced[branch], "source": "configurada en .env"}
        elif branch in from_psirt:
            latest[branch] = {"version": from_psirt[branch], "source": "avisos de WatchGuard"}
        else:
            latest[branch] = {"version": observed[branch], "source": "más alta detectada"}

    # Datos de cada aviso una sola vez; cada equipo solo lleva el ID y su corrección.
    catalog: dict[str, dict] = {}
    rows: list[dict] = []
    for d in devices:
        version, model = d.get("version"), d.get("short_model_name")
        branch = branch_of(model, version) if version else None
        target = latest.get(branch, {}).get("version") if branch else None
        found = psirt.advisories_for(advisories, model, version)
        counts: dict[str, int] = {}
        for a in found:
            counts[a["severity"]] = counts.get(a["severity"], 0) + 1
            catalog.setdefault(a["id"], {k: a[k] for k in ("url", "severity", "score", "summary")})
        critical = any(rank(a["severity"]) >= rank(settings.alert_severity) for a in found)
        updated = bool(version) and compare_versions(version, target) >= 0
        rows.append(
            {
                "id": d.get("id"),
                "name": d.get("name"),
                "model": model,
                "serial": d.get("serial_number"),
                "version": version or "—",
                "branch": branch,
                "latest": target or "—",
                "state": d.get("state"),
                "ip": d.get("public_ip_address"),
                "customer": d.get("customer"),
                "customerId": d.get("customerId"),
                "status": "critical" if critical else "updated" if updated else "outdated",
                "counts": counts,
                "advisories": [{"id": a["id"], "fix": a["fix"]} for a in found],
            }
        )
    rows.sort(key=lambda r: (STATUS_ORDER[r["status"]], (r["customer"] or "").lower(), (r["name"] or "").lower()))

    def count(status: str) -> int:
        return sum(1 for r in rows if r["status"] == status)

    return {
        "demo": settings.demo,
        "alertSeverity": settings.alert_severity,
        "latest": latest,
        "totals": {
            "total": len(rows),
            "updated": count("updated"),
            "outdated": count("outdated"),
            "critical": count("critical"),
        },
        "devices": rows,
        "advisories": catalog,
        "errors": errors,
    }


def demo_data() -> dict:
    rows = [
        ("Transportes Ruiz", "FW-Central", "M290", "2026.4", "online"),
        ("Transportes Ruiz", "FW-Almacen", "T45", "2025.1.1", "online"),
        ("Clínica San Rafael", "FW-Clinica", "M390", "2026.4", "online"),
        ("Clínica San Rafael", "FW-Consultas", "T25", "2026.3.1", "offline"),
        ("Asesoría Gómez", "FW-Oficina", "T20", "12.9.2", "online"),
        ("Colegio Montesol", "FW-Principal", "M470", "12.12.4", "online"),
        ("Colegio Montesol", "FW-Pabellon", "T45", "2026.4", "online"),
        ("Colegio Montesol", "FW-Secretaria", "T35", "12.5.22", "online"),
        ("Hotel Mirador", "FW-Recepcion", "T85", "2026.4", "online"),
        ("Hotel Mirador", "FW-Spa", "T15", "12.5.10", "never connected"),
        ("Industrias Nalón", "FW-Planta", "M590", "2026.4", "online"),
        ("Industrias Nalón", "FW-Oficinas", "M290", "12.12.3", "online"),
    ]
    customer_ids = {c: f"WGC-DEMO-{i + 1}" for i, c in enumerate(dict.fromkeys(r[0] for r in rows))}
    return {
        "devices": [
            {
                "id": f"FB-{10000 + n}",
                "name": name,
                "short_model_name": model,
                "serial_number": f"80D{1000000 + n * 7919:X}",
                "version": version,
                "state": state,
                "public_ip_address": f"203.0.113.{10 + n}",
                "customer": customer,
                "customerId": customer_ids[customer],
            }
            for n, (customer, name, model, version, state) in enumerate(rows)
        ],
        "errors": [],
    }
