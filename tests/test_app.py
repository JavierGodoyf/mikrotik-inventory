from fastapi.testclient import TestClient

from app.main import app


def test_dashboard_renders():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "equipos" in response.text.lower()


def test_device_form_renders():
    with TestClient(app) as client:
        response = client.get("/devices/new")
    assert response.status_code == 200
    assert 'name="host"' in response.text


def test_healthz_is_offline_and_fast():
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_csv_export_has_header():
    with TestClient(app) as client:
        response = client.get("/report.csv")
    assert response.status_code == 200
    assert response.text.splitlines()[0].startswith("equipo,host,red")


def test_static_css_served():
    with TestClient(app) as client:
        response = client.get("/static/style.css")
    assert response.status_code == 200
    assert "--bg" in response.text
