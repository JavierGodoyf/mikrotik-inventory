from __future__ import annotations

from .versions import Version, parse

# Arquitecturas con paquete publicado en la rama 7.x
# (verificado contra download.mikrotik.com/routeros/7.25/).
V7_ARCHITECTURES = {
    "arm",
    "arm64",
    "mipsbe",
    "mmips",
    "ppc",
    "smips",
    "tile",
    "x86",
    "chr",
}

# RouterOS 7 necesita al menos 16 MB de flash; por debajo, el salto v6 -> v7
# normalmente exige netinstall y una revisión manual.
MIN_FLASH_V7_KB = 16 * 1024


def supports_v7(architecture: str | None) -> bool:
    return (architecture or "").strip().lower() in V7_ARCHITECTURES


def flash_is_tight(free_hdd_kb: int | None) -> bool:
    return free_hdd_kb is not None and free_hdd_kb < MIN_FLASH_V7_KB


def requires_manual_review(installed: Version | None, architecture: str | None, free_hdd_kb: int | None) -> bool:
    """Salto de rama mayor: nunca lo damos por automático."""
    if installed is None or installed.major >= 7:
        return False
    return supports_v7(architecture) and flash_is_tight(free_hdd_kb)


def describe_board(architecture: str | None, board: str | None) -> str:
    parts = [p for p in (board, architecture) if p]
    return " · ".join(parts) if parts else "—"


def parse_kb(value: str | int | None) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    digits = "".join(ch for ch in value if ch.isdigit())
    return int(digits) if digits else None


def parse_version(value: str | None) -> Version | None:
    return parse(value)
