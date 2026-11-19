import uuid
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from src.api.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_serve_dashboard_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Bergag" in response.text
    assert "Portail Marocain des Marchés Publics" in response.text
    assert "dashboardApp()" in response.text
    assert "Chart.js" in response.text
    assert "formatCountdown" in response.text
    assert "export-bordereau" in response.text

def test_get_available_profiles(client):
    response = client.get("/api/profiles")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    profile_names = [p["profile_name"] for p in data]
    assert any("Vidéosurveillance" in p or "CCTV" in p for p in profile_names)
    assert any("Logiciel" in p or "Software" in p for p in profile_names)

def test_auth_login_and_roles(client):
    # Test valid Admin login
    res = client.post("/api/auth/login", json={
        "username_or_email": "admin@bergag.ma",
        "password": "AdminBergag2026!"
    })
    assert res.status_code == 200
    body = res.json()
    assert "token" in body
    assert body["user"]["role"] == "admin"
    assert "crawler:trigger" in body["user"]["permissions"]

    # Test invalid login
    res_bad = client.post("/api/auth/login", json={
        "username_or_email": "admin@bergag.ma",
        "password": "wrong_password"
    })
    assert res_bad.status_code == 401

def test_switch_demo_role(client):
    # Test Analyst switch
    res_analyst = client.post("/api/auth/switch-demo-role", json={"role": "analyst"})
    assert res_analyst.status_code == 200
    assert res_analyst.json()["user"]["role"] == "analyst"
    assert "tender:pricing_calculator" in res_analyst.json()["user"]["permissions"]

    # Test Viewer switch
    res_viewer = client.post("/api/auth/switch-demo-role", json={"role": "viewer"})
    assert res_viewer.status_code == 200
    assert res_viewer.json()["user"]["role"] == "viewer"
    assert "tender:pricing_calculator" not in res_viewer.json()["user"]["permissions"]

def test_crawler_status_rbac(client):
    res = client.get("/api/crawler/status")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "waf_status" in data

def test_admin_ingestion_dashboard(client):
    res = client.get("/api/admin/ingestion/dashboard")
    assert res.status_code == 200
    data = res.json()
    assert "freshness" in data
    assert "is_up_to_date" in data["freshness"]
    assert "quality" in data
    assert data["quality"]["overall_score"] >= 90.0
    assert len(data["quality"]["categories"]) == 3
    assert "batches" in data
    assert len(data["batches"]) > 0
    assert "diagnostic" in data
    assert "recommended_action" in data["diagnostic"]

def test_admin_ingestion_remediation(client):
    with patch("src.engine.batch_manager.run_active_crawl_cycle", new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = None
        res = client.post("/api/admin/ingestion/remediate", json={"pages": 2})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "remediation_started"

def test_admin_batch_trigger(client):
    with patch("src.engine.batch_manager.run_active_crawl_cycle", new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = None
        res = client.post("/api/admin/ingestion/batches/trigger", json={"pages": 1})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "batch_started"

