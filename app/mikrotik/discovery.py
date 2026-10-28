from __future__ import annotations

import socket
import struct
import time

TLV_NAMES = {
    1: "mac",
    5: "identity",
    7: "version",
    8: "platform",
    10: "uptime",
    11: "software_id",
    12: "board",
    13: "unpacked",
    16: "ipv6",
    17: "interface",
    18: "ipv4",
}

MNDP_PORT = 5678


class DiscoveryError(RuntimeError):
    pass


def _local_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(info[4][0])
    except OSError:
        pass
    for probe in ("1.1.1.1", "8.8.8.8"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((probe, 53))
                addresses.add(sock.getsockname()[0])
        except OSError:
            continue
    return sorted(a for a in addresses if not a.startswith("127."))


def _decode(tlv_type: int, value: bytes) -> str:
    if tlv_type == 1 and len(value) == 6:
        return ":".join(f"{b:02x}" for b in value)
    if tlv_type == 18 and len(value) == 4:
        return socket.inet_ntoa(value)
    if tlv_type == 16 and len(value) == 16:
        return socket.inet_ntop(socket.AF_INET6, value)
    if tlv_type == 10 and len(value) in (4, 8):
        seconds = int.from_bytes(value, "little")
        hours, rest = divmod(seconds, 3600)
        minutes, secs = divmod(rest, 60)
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.hex()


def _parse(payload: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    offset = 0
    while offset + 4 <= len(payload):
        tlv_type, length = struct.unpack("!HH", payload[offset : offset + 4])
        offset += 4
        value = payload[offset : offset + length]
        offset += length
        if len(value) < length:
            break
        result[TLV_NAMES.get(tlv_type, f"tlv_{tlv_type}")] = _decode(tlv_type, value)
    return result


def discover(timeout: float = 4.0) -> list[dict[str, str]]:
    """Descubre vecinos MikroTik por MNDP (UDP 5678). No necesita credenciales."""
    found: dict[str, dict[str, str]] = {}
    errors: list[str] = []

    targets = {"255.255.255.255"}
    local_addresses = _local_ipv4_addresses()
    for address in local_addresses:
        octets = address.split(".")
        if len(octets) == 4:
            targets.add(".".join(octets[:3] + ["255"]))

    sockets: list[socket.socket] = []
    try:
        for address in [None, *local_addresses]:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if address:
                try:
                    sock.bind((address, 0))
                except OSError:
                    sock.close()
                    continue
            sock.setblocking(False)
            sockets.append(sock)

        for sock in sockets:
            for target in targets:
                try:
                    sock.sendto(b"\x00\x00\x00\x00", (target, MNDP_PORT))
                except OSError as exc:
                    errors.append(f"{target}: {exc}")

        deadline = time.time() + timeout
        while time.time() < deadline:
            received = False
            for sock in sockets:
                try:
                    payload, source = sock.recvfrom(8192)
                except (BlockingIOError, InterruptedError):
                    continue
                except OSError as exc:
                    errors.append(str(exc))
                    continue
                received = True
                data = _parse(payload)
                if not data:
                    continue
                data.setdefault("ipv4", source[0])
                found[data.get("mac") or source[0]] = data
            if not received:
                time.sleep(0.05)
    finally:
        for sock in sockets:
            sock.close()

    if not found and errors and all("route to host" in e or "No route to host" in e for e in errors):
        raise DiscoveryError(
            "macOS está bloqueando el acceso a la red local para este proceso. "
            "Ajustes > Privacidad y seguridad > Red local: activa el permiso y reinicia OpenCode."
        )

    return sorted(found.values(), key=lambda d: (d.get("identity") or d.get("ipv4") or ""))
