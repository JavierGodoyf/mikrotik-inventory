from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.watchguard import service
from app.watchguard.config import WatchGuardSettings
from app.watchguard.summary import demo_data, summarize

ADVISORIES = [
    {
        "id": "WGSA-TEST-1",
        "url": "https://psirt.watchguard.com/WGSA-TEST-1/",
        "severity": "critical",
        "score": "9.8",
        "summary": "Fallo crítico",
        "platforms": {
            "Default": {
                "affected": [{"min": "2025.1", "min_inc": True, "max": "2026.4", "max_inc": False}],
                "not_affected": ["2026.4"],
            }
        },
    }
]


def test_summarize_demo_marks_critical_and_updated():
    settings = WatchGuardSettings(demo=True, psirt=False)
    data = summarize(demo_data(), ADVISORIES, settings)
    by_name = {d["name"]: d for d in data["devices"]}

    assert data["totals"]["total"] == 12
    assert by_name["FW-Almacen"]["status"] == "critical"  # 2025.1.1 afectado
    assert by_name["FW-Almacen"]["advisories"] == [{"id": "WGSA-TEST-1", "fix": "2026.4"}]
    assert by_name["FW-Central"]["status"] == "updated"  # 2026.4 corregido
    assert by_name["FW-Oficinas"]["status"] == "outdated"  # 12.12.3 < 12.12.4 observado
    assert data["latest"]["actual"] == {"version": "2026.4", "source": "avisos de WatchGuard"}
    assert data["advisories"]["WGSA-TEST-1"]["severity"] == "critical"
    # Los críticos van primero.
    assert data["devices"][0]["status"] == "critical"


def test_manual_latest_wins_over_advisories():
    settings = WatchGuardSettings(demo=True, latest_fireware="2026.5,12.12.4,12.5.22")
    data = summarize(demo_data(), ADVISORIES, settings)
    assert data["latest"]["actual"]["version"] == "2026.5"
    assert data["latest"]["T15/T35"]["version"] == "12.5.22"


def test_token_url_and_base_url():
    settings = WatchGuardSettings(base_url="https://api.eu.cloud.watchguard.com/rest/")
    assert settings.api_base == "https://api.eu.cloud.watchguard.com"
    assert settings.token_url == "https://api.eu.cloud.watchguard.com/oauth/token"
    assert WatchGuardSettings(auth_url="https://x/oauth/token").token_url == "https://x/oauth/token"


def test_refresh_stores_run_and_api_returns_it():
    init_db()
    run = service.refresh()
    assert run is not None and run.ok and run.total == 12

    with TestClient(app) as client:
        payload = client.get("/api/watchguard").json()
        page = client.get("/watchguard")
        health = client.get("/healthz").json()
        nav = client.get("/").text

    assert payload["totals"]["total"] == 12
    assert payload["demo"] is True and payload["stale"] is False
    assert payload["checkedAt"].endswith("Z")
    assert page.status_code == 200 and 'id="wg-table"' in page.text
    assert health["watchguard"]["devices"] == 12
    assert 'href="/watchguard"' in nav


def test_refresh_endpoint_redirects():
    with TestClient(app) as client:
        response = client.post("/watchguard/refresh", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/watchguard?msg=")
