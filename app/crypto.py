from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

_fernet: Fernet | None = None


def _load_key() -> bytes:
    path = Path(get_settings().key_file)
    if path.exists():
        return path.read_bytes().strip()
    key = Fernet.generate_key()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    os.chmod(path, 0o600)
    return key


def _cipher() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_key())
    return _fernet


def encrypt(plain: str) -> str:
    return _cipher().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _cipher().decrypt(token.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - depende de la clave local
        raise ValueError(
            "No se puede descifrar la contraseña: la clave de data/secret.key "
            "no coincide con la que cifró los datos."
        ) from exc
