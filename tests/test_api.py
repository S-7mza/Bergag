import uuid
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from src.api.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_serve_dashboard_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Antigravity Procurement" in response.text
    assert "Portail Marocain des Marchés Publics" in response.text
    assert "dashboardApp()" in response.text

def test_get_available_profiles(client):
    response = client.get("/api/profiles")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    profile_names = [p["profile_name"] for p in data]
    assert any("Vidéosurveillance" in p or "CCTV" in p for p in profile_names)
    assert any("Logiciel" in p or "Software" in p for p in profile_names)
