from __future__ import annotations

from dataclasses import dataclass

from .compat import requires_manual_review, supports_v7
from .versions import Version, is_newer, parse

STATUS_UNREACHABLE = "unreachable"
STATUS_OK = "ok"
STATUS_AHEAD = "ahead"
STATUS_OUTDATED = "outdated"
STATUS_V6_FINAL = "outdated_v6_final"
STATUS_MANUAL = "manual_review"
STATUS_UNKNOWN = "unknown"

STATUS_LABELS: dict[str, str] = {
    STATUS_OK: "Actualizado",
    STATUS_AHEAD: "Adelantado",
    STATUS_OUTDATED: "Actualizable",
    STATUS_V6_FINAL: "Sin ruta a v7",
    STATUS_MANUAL: "Revisión manual",
    STATUS_UNREACHABLE: "Inalcanzable",
    STATUS_UNKNOWN: "Desconocido",
}

STATUS_CSS: dict[str, str] = {
    STATUS_OK: "ok",
    STATUS_AHEAD: "info",
    STATUS_OUTDATED: "warn",
    STATUS_V6_FINAL: "end",
    STATUS_MANUAL: "info",
    STATUS_UNREACHABLE: "bad",
    STATUS_UNKNOWN: "muted",
}

# Orden de gravedad para los contadores del dashboard
STATUS_ORDER = [
    STATUS_UNREACHABLE,
    STATUS_OUTDATED,
    STATUS_V6_FINAL,
    STATUS_MANUAL,
    STATUS_AHEAD,
    STATUS_OK,
    STATUS_UNKNOWN,
]


@dataclass
class Evaluation:
    status: str
    target_version: str | None
    target_source: str | None
    message: str
    routerboot_outdated: bool = False


def _target_channel(preferred: str, available: dict[str, str]) -> str | None:
    if preferred in available:
        return preferred
    if "stable" in available:
        return "stable"
    return next(iter(available), None)


def evaluate(
    *,
    installed_version: str | None,
    architecture: str | None,
    free_hdd_kb: int | None,
    preferred_channel: str,
    latest: dict[str, str],
    reported_latest: str | None = None,
    routerboot_current: str | None = None,
    routerboot_upgrade: str | None = None,
) -> Evaluation:
    installed = parse(installed_version)
    if installed is None:
        return Evaluation(STATUS_UNKNOWN, None, None, "El router no devolvió una versión válida.")

    channel = _target_channel(preferred_channel, latest)
    target_raw = latest.get(channel) if channel else None
    source = "upstream"

    # Si el propio router ya consultó a MikroTik y ve algo más nuevo, mandamos nosotros.
    if reported_latest and is_newer(reported_latest, target_raw):
        target_raw = reported_latest
        source = "router"

    target = parse(target_raw)
    boot_outdated = is_newer(routerboot_upgrade, routerboot_current)
    boot_note = " RouterBOOT también está desfasado." if boot_outdated else ""

    if target is None:
        return Evaluation(
            STATUS_UNKNOWN,
            None,
            None,
            "No se pudo determinar la última versión disponible." + boot_note,
            boot_outdated,
        )

    if installed == target:
        if installed.major < 7 and not supports_v7(architecture):
            return Evaluation(
                STATUS_OK,
                str(target),
                source,
                "Está en la última versión de la rama v6; este equipo no tiene ruta a v7." + boot_note,
                boot_outdated,
            )
        return Evaluation(STATUS_OK, str(target), source, "Al día." + boot_note, boot_outdated)

    if installed > target:
        return Evaluation(
            STATUS_AHEAD,
            str(target),
            source,
            f"Tiene una versión más nueva ({installed}) que la publicada en el canal." + boot_note,
            boot_outdated,
        )

    # installed < target
    if installed.major < 7:
        if not supports_v7(architecture):
            return Evaluation(
                STATUS_V6_FINAL,
                str(target),
                source,
                f"Puede subir a {target} dentro de v6, pero no hay ruta a v7 para "
                f"'{architecture or 'arquitectura desconocida'}'." + boot_note,
                boot_outdated,
            )
        if requires_manual_review(installed, architecture, free_hdd_kb):
            return Evaluation(
                STATUS_MANUAL,
                str(target),
                source,
                f"Salto de v{installed.major} a {target} con poco espacio libre. "
                "Probablemente necesite netinstall y una ventana de mantenimiento." + boot_note,
                boot_outdated,
            )
        return Evaluation(
            STATUS_MANUAL,
            str(target),
            source,
            f"Salto de v{installed.major} a {target}: revisar compatibilidad de la placa "
            "y hacerlo en ventana de mantenimiento." + boot_note,
            boot_outdated,
        )

    return Evaluation(
        STATUS_OUTDATED,
        str(target),
        source,
        f"Hay versión nueva: {installed} → {target}." + boot_note,
        boot_outdated,
    )


@dataclass
class SnapshotView:
    installed_version: str | None
    architecture: str | None
    free_hdd_kb: int | None
    reported_latest: str | None
    routerboot_current: str | None
    routerboot_upgrade: str | None


def evaluate_snapshot(snapshot: SnapshotView, preferred_channel: str, latest: dict[str, str]) -> Evaluation:
    return evaluate(
        installed_version=snapshot.installed_version,
        architecture=snapshot.architecture,
        free_hdd_kb=snapshot.free_hdd_kb,
        preferred_channel=preferred_channel,
        latest=latest,
        reported_latest=snapshot.reported_latest,
        routerboot_current=snapshot.routerboot_current,
        routerboot_upgrade=snapshot.routerboot_upgrade,
    )


def target_line(installed_version: str | None, architecture: str | None) -> str:
    """Rama contra la que comparamos: 7 si el equipo puede, 6 si es su techo."""
    installed: Version | None = parse(installed_version)
    if installed is not None and installed.major >= 7:
        return "7"
    return "7" if supports_v7(architecture) else "6"
