from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from urllib.parse import quote

import httpx

from .config import WatchGuardSettings

ACCOUNT_CONCURRENCY = 5  # consultas en paralelo a la API; más satura el rate limit de WatchGuard


class WatchGuardError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class WatchGuardClient:
    """Cliente de solo lectura de la API de WatchGuard Cloud para un Service Provider."""

    def __init__(self, settings: WatchGuardSettings):
        self.settings = settings
        self._http = httpx.Client(timeout=settings.timeout, headers={"Accept": "application/json"})
        self._tokens: dict[str, tuple[str, float]] = {}  # audiencia ("" = cuenta propia) -> (token, caduca)
        self._token_lock = Lock()

    def __enter__(self) -> WatchGuardClient:
        return self

    def __exit__(self, *exc) -> None:
        self._http.close()

    def token(self, audience: str = "") -> str:
        with self._token_lock:
            cached = self._tokens.get(audience)
            if cached and cached[1] > time.time() + 60:
                return cached[0]
            data = {"grant_type": "client_credentials", "scope": "api-access"}
            if audience:
                data["audience"] = audience
            try:
                response = self._http.post(
                    self.settings.token_url,
                    data=data,
                    auth=(self.settings.access_id, self.settings.password),
                )
            except httpx.HTTPError as exc:
                raise WatchGuardError(f"No se pudo contactar con {self.settings.token_url}: {exc}") from exc
            if response.status_code >= 400:
                raise WatchGuardError(
                    f"Error de autenticación ({response.status_code}): {response.text}", response.status_code
                )
            body = response.json()
            self._tokens[audience] = (body["access_token"], time.time() + (body.get("expires_in") or 3600))
            return body["access_token"]

    def api(self, path: str, *, token: str | None = None, method: str = "GET", json: dict | None = None) -> dict:
        try:
            response = self._http.request(
                method,
                self.settings.api_base + path,
                json=json,
                headers={
                    "Authorization": f"Bearer {token or self.token()}",
                    "WatchGuard-API-Key": self.settings.api_key,
                },
            )
        except httpx.HTTPError as exc:
            raise WatchGuardError(f"{method} {path}: {exc}") from exc
        if response.status_code >= 400:
            raise WatchGuardError(f"{method} {path} -> {response.status_code}: {response.text}", response.status_code)
        # La API a veces responde 200 con {"status":"error","errors":[...]}.
        body = response.json()
        if isinstance(body, dict) and body.get("status") == "error":
            errors = body.get("errors") or []
            detail = "; ".join(f"{e.get('code')}: {e.get('message')}" for e in errors)
            code = errors[0].get("code") if errors else None
            raise WatchGuardError(f"{method} {path} -> {detail}", 401 if code == 401 else response.status_code)
        return body

    def customers(self) -> list[dict]:
        """Recorre el árbol de cuentas hijas (clientes) del Service Provider."""
        account = quote(self.settings.account_id, safe="")
        body = self.api(f"/rest/platform/accounts/v2/accounts/{account}/children?limit=-1&includeDelegatedAccounts=true")
        out: list[dict] = []

        def walk(items: list[dict] | None) -> None:
            for item in items or []:
                out.append({"accountId": item.get("accountId"), "name": item.get("name"), "type": item.get("type")})
                walk(item.get("childrenList"))

        walk(body.get("items"))
        return out

    def devices(self, account_id: str) -> list[dict]:
        """Fireboxes de una cuenta. Si el token del SP no basta, pide uno con la audiencia del cliente."""
        path = f"/rest/firebox/management/v1/info/{quote(account_id, safe='')}/devices?device_type=FB"
        try:
            return self.api(path).get("data") or []
        except WatchGuardError as exc:
            if account_id == self.settings.account_id or exc.status not in (401, 403):
                raise
            audience = self.api(
                "/rest/platform/authorization/v1/audiences", method="POST", json={"accountId": account_id}
            )["audience"]
            return self.api(path, token=self.token(audience)).get("data") or []

    def collect(self) -> dict:
        """Todos los Fireboxes de la cuenta propia y de sus clientes, con los errores por cuenta."""
        accounts = [{"accountId": self.settings.account_id, "name": "Cuenta propia"}, *self.customers()]
        devices: list[dict] = []
        errors: list[dict] = []

        def fetch(account: dict) -> tuple[dict, list[dict], Exception | None]:
            try:
                return account, self.devices(account["accountId"]), None
            except Exception as exc:  # un cliente que falla no debe tumbar el resto
                return account, [], exc

        with ThreadPoolExecutor(max_workers=ACCOUNT_CONCURRENCY) as pool:
            for account, found, error in pool.map(fetch, accounts):
                if error:
                    errors.append({"customer": account["name"], "error": str(error)[:300]})
                devices += [{**d, "customer": account["name"], "customerId": account["accountId"]} for d in found]
        return {"devices": devices, "errors": errors}
