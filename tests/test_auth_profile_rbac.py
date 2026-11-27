import pytest
from unittest.mock import patch
from starlette.testclient import TestClient

from src.api.main import app
from src.api.auth import (
    SYSTEM_USERS,
    _LOGIN_FAILURES,
    create_session_token,
    set_user_profile_scope,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_profiles_endpoint_returns_dynamic_weights_and_samples(client):
    admin_token = create_session_token("admin@bergag.ma", "admin")
    res = client.get("/api/profiles", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    profiles = res.json()

    by_id = {p["id"]: p for p in profiles}
    assert "special_ai_hybrid" in by_id
    assert "cctv_security" in by_id
    assert "software_data" in by_id

    hybrid = by_id["special_ai_hybrid"]
    assert hybrid["scoring_mode"] == "hybrid"
    assert hybrid["file_name"] == "special_ai_hybrid.yaml"
    assert "ai_engine_weight" in hybrid["scoring_weights"]
    assert len(hybrid["positive_keywords_sample"]) > 0
    assert len(hybrid["negative_keywords_sample"]) > 0


def test_profile_based_rbac_restricts_viewer_to_assigned_profiles(client):
    # Restrict viewer@bergag.ma strictly to cctv_security
    set_user_profile_scope(
        "viewer@bergag.ma",
        default_profile="cctv_security",
        allowed_profiles=["cctv_security"],
    )
    viewer_token = create_session_token("viewer@bergag.ma", "viewer")

    # 1. GET /api/profiles only returns cctv_security
    res_list = client.get("/api/profiles", headers={"Authorization": f"Bearer {viewer_token}"})
    assert res_list.status_code == 200
    ids = [p["id"] for p in res_list.json()]
    assert ids == ["cctv_security"]

    # 2. Accessing authorized profile succeeds
    res_ok = client.get("/api/profiles/cctv_security", headers={"Authorization": f"Bearer {viewer_token}"})
    assert res_ok.status_code == 200

    # 3. Accessing unauthorized profile is denied (403)
    res_denied = client.get("/api/profiles/software_data", headers={"Authorization": f"Bearer {viewer_token}"})
    assert res_denied.status_code == 403

    # 4. Feed request for unauthorized profile is denied (403)
    res_feed_denied = client.get(
        "/api/feed?profile_name=software_data",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert res_feed_denied.status_code == 403

    # 5. Viewer cannot mutate YAML profile rules (403)
    res_put_denied = client.put(
        "/api/profiles/cctv_security",
        json={"profile_name": "Hacked"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert res_put_denied.status_code == 403


def test_deactivated_user_rejected_even_with_valid_token(client):
    token = create_session_token("analyst@bergag.ma", "analyst")
    orig_active = SYSTEM_USERS["analyst@bergag.ma"].get("is_active", True)
    try:
        SYSTEM_USERS["analyst@bergag.ma"]["is_active"] = False
        with patch("src.api.auth.find_user_in_db", return_value=None):
            res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert res.status_code == 403
    finally:
        SYSTEM_USERS["analyst@bergag.ma"]["is_active"] = orig_active


def test_login_rate_limiting_blocks_bruteforce(client):
    _LOGIN_FAILURES.clear()
    for _ in range(5):
        res = client.post(
            "/api/auth/login",
            json={"username_or_email": "bruteforce_target@bergag.ma", "password": "wrong"},
        )
        assert res.status_code == 401

    # 6th attempt must be rate-limited (429)
    res_blocked = client.post(
        "/api/auth/login",
        json={"username_or_email": "bruteforce_target@bergag.ma", "password": "wrong"},
    )
    assert res_blocked.status_code == 429
    _LOGIN_FAILURES.clear()


def test_admin_can_update_user_profile_access(client):
    admin_token = create_session_token("admin@bergag.ma", "admin")
    with patch("src.api.routes.auth.select") as _:
        res = client.put(
            "/api/auth/users/viewer@bergag.ma/access",
            json={
                "role": "analyst",
                "is_active": True,
                "default_profile": "software_data",
                "allowed_profiles": ["software_data", "special_ai_hybrid"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["role"] == "analyst"
        assert data["default_profile"] == "software_data"
        assert "software_data" in data["allowed_profiles"]

    # Restore viewer@bergag.ma role
    client.put(
        "/api/auth/users/viewer@bergag.ma/access",
        json={
            "role": "viewer",
            "is_active": True,
            "default_profile": "cctv_security",
            "allowed_profiles": ["cctv_security", "software_data", "special_ai_hybrid"],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )


def test_login_form_ui_and_username_password_role_resolution(client):
    from unittest.mock import AsyncMock, MagicMock
    from src.database.session import get_db_session

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_res
    app.dependency_overrides[get_db_session] = lambda: mock_session

    try:
        # 1. Verify UI renders the username/password login form
        page = client.get("/")
        assert page.status_code == 200
        assert "submitLogin()" in page.text
        assert "loginForm.username_or_email" in page.text
        assert "loginForm.password" in page.text

        # 2. Authenticate with username + password for each role
        for uname, pwd, expected_role in [
            ("hamza", "AdminBergag2026!", "admin"),
            ("analyst", "Analyst2026!", "analyst"),
            ("viewer", "Viewer2026!", "viewer"),
        ]:
            login_res = client.post(
                "/api/auth/login",
                json={"username_or_email": uname, "password": pwd},
            )
            assert login_res.status_code == 200
            payload = login_res.json()
            assert payload["user"]["role"] == expected_role
            assert payload["token"]

            me_res = client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {payload['token']}"},
            )
            assert me_res.status_code == 200
            assert me_res.json()["role"] == expected_role
    finally:
        app.dependency_overrides.pop(get_db_session, None)
