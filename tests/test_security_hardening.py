from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.auth import create_session_token
from src.api.main import app
from src.config.settings import settings
from src.database.session import get_db_session


@pytest.fixture
def client():
    return TestClient(app)


def _mock_empty_db():
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_res
    return mock_session


def test_anonymous_dev_admin_disabled_by_default():
    assert settings.allow_anonymous_dev_admin is False


def test_rootpassword_backdoor_rejected(client):
    app.dependency_overrides[get_db_session] = _mock_empty_db
    try:
        res = client.post(
            "/api/auth/login",
            json={"username_or_email": "admin@bergag.ma", "password": "rootpassword"},
        )
        assert res.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_switch_demo_role_disabled_in_production(client):
    res = client.post("/api/auth/switch-demo-role", json={"role": "admin"})
    assert res.status_code == 403


def test_unauthenticated_requests_rejected_on_protected_endpoints(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/users").status_code == 401
    assert client.post("/api/agent/diagnose-batch", json={"limit": 5}).status_code == 401
    assert client.post("/api/agent/sync-db?limit=5").status_code == 401


def test_agent_mutation_endpoints_enforce_rbac(client):
    viewer_headers = {"Authorization": f"Bearer {create_session_token('viewer@bergag.ma', 'viewer')}"}
    analyst_headers = {"Authorization": f"Bearer {create_session_token('analyst@bergag.ma', 'analyst')}"}

    # Viewer cannot run diagnose-batch or sync-db
    assert client.post("/api/agent/diagnose-batch", json={"limit": 5}, headers=viewer_headers).status_code == 403
    assert client.post("/api/agent/sync-db?limit=5", headers=viewer_headers).status_code == 403

    # Analyst cannot run sync-db (admin-only)
    assert client.post("/api/agent/sync-db?limit=5", headers=analyst_headers).status_code == 403


def test_security_headers_present(client):
    app.dependency_overrides[get_db_session] = _mock_empty_db
    try:
        res = client.get("/")
        assert res.status_code == 200
        assert res.headers.get("x-content-type-options") == "nosniff"
        assert res.headers.get("x-frame-options") == "DENY"
        assert res.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
