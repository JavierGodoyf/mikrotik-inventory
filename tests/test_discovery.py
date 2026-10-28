import socket
import struct

from app.mikrotik.discovery import _parse


def tlv(tlv_type: int, value: bytes) -> bytes:
    return struct.pack("!HH", tlv_type, len(value)) + value


def test_parse_mndp_payload():
    payload = b"".join(
        [
            tlv(1, bytes.fromhex("d41c3c56797a")),
            tlv(5, b"hAP-oficina"),
            tlv(7, b"7.16.2"),
            tlv(8, b"MikroTik"),
            tlv(12, b"RB952Ui-5ac2nD"),
            tlv(18, socket.inet_aton("192.168.1.1")),
        ]
    )
    data = _parse(payload)
    assert data["mac"] == "d4:1c:3c:56:79:7a"
    assert data["identity"] == "hAP-oficina"
    assert data["version"] == "7.16.2"
    assert data["board"] == "RB952Ui-5ac2nD"
    assert data["ipv4"] == "192.168.1.1"


def test_parse_ignores_truncated_tlv():
    payload = tlv(5, b"abc") + b"\x00\x05\x00\x20xyz"
    assert _parse(payload) == {"identity": "abc"}
