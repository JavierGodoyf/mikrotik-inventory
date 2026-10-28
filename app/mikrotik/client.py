from __future__ import annotations

import errno
import socket
import ssl
from dataclasses import dataclass

import librouteros

LOCAL_NETWORK_HINT = (
    " macOS está bloqueando el acceso a la red local para este proceso. "
    "Arranca el panel desde Terminal.app y acepta el permiso de 'Red local' "
    "(Ajustes > Privacidad y seguridad > Red local), o activa ahí la app que lo ejecuta."
)


class MikrotikError(RuntimeError):
    """Error de conexión o de credenciales, ya traducido a algo legible."""


@dataclass
class Credentials:
    host: str
    username: str
    password: str
    port: int = 8728
    transport: str = "api"  # api | api_ssl
    verify_tls: bool = False
    timeout: float = 8.0


def _ssl_wrapper(verify: bool):
    context = ssl.create_default_context()
    if not verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context.wrap_socket


def connect(credentials: Credentials):
    wrapper = _ssl_wrapper(credentials.verify_tls) if credentials.transport == "api_ssl" else None
    try:
        return librouteros.connect(
            host=credentials.host,
            username=credentials.username,
            password=credentials.password,
            port=credentials.port,
            timeout=credentials.timeout,
            ssl_wrapper=wrapper,
        )
    except socket.timeout as exc:
        raise MikrotikError(f"Timeout al conectar con {credentials.host}:{credentials.port}") from exc
    except ssl.SSLError as exc:
        raise MikrotikError(f"Error TLS con {credentials.host}:{credentials.port}: {exc}") from exc
    except ConnectionRefusedError as exc:
        raise MikrotikError(f"Conexión rechazada en {credentials.host}:{credentials.port}") from exc
    except OSError as exc:
        hint = LOCAL_NETWORK_HINT if exc.errno in (errno.EHOSTUNREACH, errno.ENETUNREACH) else ""
        raise MikrotikError(
            f"No se pudo conectar con {credentials.host}:{credentials.port}: {exc}.{hint}"
        ) from exc
    except Exception as exc:  # librouteros traduce los !trap en sus propias excepciones
        raise MikrotikError(f"Fallo al iniciar sesión en {credentials.host}: {exc}") from exc
