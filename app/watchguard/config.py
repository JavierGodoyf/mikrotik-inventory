from __future__ import annotations

import re
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..config import BASE_DIR, get_settings
from .psirt import SEVERITIES


class WatchGuardSettings(BaseSettings):
    """Datos de WatchGuard Cloud > Administración > Managed Access (prefijo WG_)."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_prefix="WG_",
        extra="ignore",
    )

    # Vacío = se activa solo si hay credenciales o modo demo.
    enabled: bool | None = None
    # Equipos de ejemplo sin llamar a la API (los avisos PSIRT sí son reales).
    demo: bool = False

    base_url: str = "https://api.usa.cloud.watchguard.com"
    # Se admite con o sin "/oauth/token" al final; vacío = el mismo dominio que base_url.
    auth_url: str = ""
    account_id: str = ""
    access_id: str = ""
    password: str = ""
    api_key: str = ""

    # Versiones forzadas a mano, una por rama (p. ej. "2026.4,12.12.4,12.5.22").
    # Vacío = se obtienen de los avisos de WatchGuard.
    latest_fireware: str = ""
    # Gravedad mínima de un aviso para marcar un equipo como crítico: critical o high.
    alert_severity: str = "critical"
    psirt: bool = True
    psirt_cache_hours: float = 6

    # Vacío = el mismo intervalo que los MikroTik (MTIK_CHECK_INTERVAL_HOURS).
    check_interval_hours: float | None = None
    timeout: float = 20

    @field_validator("alert_severity")
    @classmethod
    def _severity(cls, value: str) -> str:
        return value if value in SEVERITIES else "critical"

    @property
    def api_base(self) -> str:
        # Managed Access muestra la URL base con "/rest" al final; las rutas ya lo incluyen.
        return re.sub(r"/rest$", "", self.base_url.rstrip("/"))

    @property
    def token_url(self) -> str:
        url = (self.auth_url or self.api_base).rstrip("/")
        return url if url.endswith("/oauth/token") else f"{url}/oauth/token"

    @property
    def has_credentials(self) -> bool:
        return all((self.account_id, self.access_id, self.password, self.api_key))

    @property
    def active(self) -> bool:
        if self.enabled is not None:
            return self.enabled
        return self.demo or self.has_credentials

    @property
    def interval_hours(self) -> float:
        return self.check_interval_hours or get_settings().check_interval_hours


@lru_cache
def get_wg_settings() -> WatchGuardSettings:
    return WatchGuardSettings()
