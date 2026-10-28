from __future__ import annotations

import argparse
import errno
import getpass
import socket
import sys

from sqlalchemy import select

from .checker import check_all, check_device
from .config import get_settings
from .crypto import encrypt
from .db import SessionLocal, init_db
from .evaluate import STATUS_LABELS
from .mikrotik.client import LOCAL_NETWORK_HINT
from .mikrotik.discovery import DiscoveryError, discover
from .models import Check, Device
from .upstream import fetch_latest


def _fmt(value, width: int) -> str:
    text = "—" if value in (None, "") else str(value)
    return text[:width].ljust(width)


def cmd_add(args: argparse.Namespace) -> int:
    password = args.password or getpass.getpass("Contraseña del usuario RouterOS: ")
    with SessionLocal() as session:
        device = Device(
            name=args.name,
            host=args.host,
            port=args.port or (8729 if args.transport == "api_ssl" else 8728),
            transport=args.transport,
            username=args.username,
            secret=encrypt(password),
            network=args.network,
            channel=args.channel,
            site=args.site or "",
            tags=args.tags or "",
            notes=args.notes or "",
            enabled=True,
        )
        session.add(device)
        session.commit()
        print(f"Equipo '{device.name}' añadido con id={device.id}.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    with SessionLocal() as session:
        devices = session.scalars(select(Device).order_by(Device.name)).all()
        if not devices:
            print("No hay equipos. Añade uno con: python -m app.cli add --name ... --host ...")
            return 0
        print(
            f"{'ID':>3}  {_fmt('NOMBRE', 20)} {_fmt('HOST', 18)} {_fmt('RED', 6)} "
            f"{_fmt('CANAL', 9)} {_fmt('INSTALADA', 11)} {_fmt('OBJETIVO', 11)} ESTADO"
        )
        for device in devices:
            check = session.scalar(
                select(Check)
                .where(Check.device_id == device.id)
                .order_by(Check.started_at.desc())
                .limit(1)
            )
            status = STATUS_LABELS.get(check.status, check.status) if check else "Sin datos"
            print(
                f"{device.id:>3}  {_fmt(device.name, 20)} {_fmt(device.host, 18)} "
                f"{_fmt(device.network, 6)} {_fmt(device.channel, 9)} "
                f"{_fmt(check.installed_version if check else None, 11)} "
                f"{_fmt(check.target_version if check else None, 11)} {status}"
            )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    if args.id:
        with SessionLocal() as session:
            device = session.get(Device, args.id)
            if device is None:
                print(f"No existe el equipo id={args.id}", file=sys.stderr)
                return 1
            check = check_device(session, device)
            if check.status == "unreachable":
                print(f"{device.name}: SIN CONEXIÓN — {check.error}")
            else:
                print(
                    f"{device.name}: {check.installed_version} → {check.target_version} "
                    f"[{STATUS_LABELS.get(check.status, check.status)}] {check.message}"
                )
        return 0

    total = check_all()
    print(f"Comprobados {total} equipos.")
    return 0


def cmd_latest(args: argparse.Namespace) -> int:
    for line in ("7", "6"):
        for channel in ("stable", "long-term"):
            try:
                version, released = fetch_latest(channel, line)
            except Exception as exc:
                print(f"{line}/{channel}: error — {exc}")
                continue
            when = released.strftime("%Y-%m-%d") if released else "?"
            print(f"{line}/{channel}: {version}  ({when})")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    try:
        devices = discover(timeout=args.timeout)
    except DiscoveryError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not devices:
        print("No se ha encontrado ningún vecino MNDP.")
        return 0
    print(f"{'IDENTITY':22} {'IPV4':16} {'VERSION':10} {'BOARD':20} PLATFORM")
    for item in devices:
        print(
            f"{_fmt(item.get('identity'), 22)} {_fmt(item.get('ipv4'), 16)} "
            f"{_fmt(item.get('version'), 10)} {_fmt(item.get('board'), 20)} {item.get('platform', '')}"
        )
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Comprueba si este proceso puede salir a internet y llegar al router."""
    host, port = args.host, args.port
    ok = True

    try:
        socket.create_connection(("1.1.1.1", 443), timeout=4).close()
        print("Internet: OK")
    except OSError as exc:
        print(f"Internet: FALLO — {exc}")
        ok = False

    try:
        with socket.create_connection((host, port), timeout=4):
            print(f"{host}:{port}: OK")
    except OSError as exc:
        print(f"{host}:{port}: FALLO — {type(exc).__name__}: {exc}")
        if exc.errno in (errno.EHOSTUNREACH, errno.ENETUNREACH):
            print("→" + LOCAL_NETWORK_HINT)
        ok = False

    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="MikroTik Inventory CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="Añadir un equipo")
    add.add_argument("--name", required=True)
    add.add_argument("--host", required=True)
    add.add_argument("--port", type=int, default=0)
    add.add_argument("--transport", choices=("api", "api_ssl"), default="api")
    add.add_argument("--username", default="panel")
    add.add_argument("--password")
    add.add_argument("--network", choices=("lan", "public"), default="lan")
    add.add_argument("--channel", choices=("stable", "long-term"), default="stable")
    add.add_argument("--site", default="")
    add.add_argument("--tags", default="")
    add.add_argument("--notes", default="")
    add.set_defaults(func=cmd_add)

    listing = sub.add_parser("list", help="Listar equipos y último estado")
    listing.set_defaults(func=cmd_list)

    check = sub.add_parser("check", help="Comprobar uno o todos los equipos")
    check.add_argument("--id", type=int)
    check.set_defaults(func=cmd_check)

    latest = sub.add_parser("latest", help="Ver versiones publicadas por MikroTik")
    latest.set_defaults(func=cmd_latest)

    discovery = sub.add_parser("discover", help="Descubrir vecinos por MNDP en la LAN")
    discovery.add_argument("--timeout", type=float, default=4.0)
    discovery.set_defaults(func=cmd_discover)

    doctor = sub.add_parser("doctor", help="Diagnosticar red local e internet")
    doctor.add_argument("--host", default="192.168.1.1")
    doctor.add_argument("--port", type=int, default=8728)
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    if not settings.db_url:
        print("Configuración inválida", file=sys.stderr)
        return 1
    init_db()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
