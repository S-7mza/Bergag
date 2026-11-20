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
    assert "checkUrlHash" in response.text
    assert "copyFicheLink" in response.text
    assert "Portail TGR" in response.text

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
    assert "gap_analysis" in data
    gap = data["gap_analysis"]
    assert "today_completion" in gap
    assert "db_latest" in gap
    assert "portal_latest" in gap
    assert gap["date_basis"] == "registration_date"
    assert "registration_date" in gap["db_latest"]

def test_admin_probe_portal_gap(client):
    res = client.post("/api/admin/ingestion/probe-portal-gap")
    assert res.status_code == 200
    data = res.json()
    assert "missing_rows" in data
    assert "batches_needed" in data
    assert "today_completion" in data
    assert "completion_pct" in data["today_completion"]
    assert data["date_basis"] == "registration_date"

def test_admin_get_gap_analysis(client):
    res = client.get("/api/admin/ingestion/gap-analysis")
    assert res.status_code == 200
    data = res.json()
    assert "range_text" in data
    assert "db_latest" in data
    assert "portal_latest" in data

def test_admin_audit_date_endpoint(client):
    # Test Day Mode
    res = client.get("/api/admin/ingestion/audit-date?date=19/11/2026&mode=day")
    assert res.status_code == 200
    data = res.json()
    assert data["target_date"] == "19/11/2026"
    assert data["period_mode"] == "day"
    assert "portal_total_published" in data
    assert "db_total_ingested" in data
    assert "concordance_pct" in data
    assert "verdict" in data
    assert "reconciled_items" in data

    # Test Range Mode
    res_range = client.get("/api/admin/ingestion/audit-date?date=14/11/2026&end_date=20/11/2026&mode=range")
    assert res_range.status_code == 200
    data_range = res_range.json()
    assert data_range["period_mode"] == "range"
    assert data_range["target_date"] == "14/11/2026"
    assert data_range["end_date"] == "20/11/2026"
    assert "Période" in data_range["period_label"]

    # Test Month Mode
    res_month = client.get("/api/admin/ingestion/audit-date?date=11/2026&mode=month")
    assert res_month.status_code == 200
    data_month = res_month.json()
    assert data_month["period_mode"] == "month"
    assert "Novembre" in data_month["period_label"]

def test_admin_reconcile_missing_items(client):
    res = client.post("/api/admin/ingestion/audit-date/reconcile", json={
        "date": "19/11/2026",
        "portal_ids": []
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "noop"

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


@pytest.mark.asyncio
async def test_batch_manager_cards_accumulation():
    from src.engine.batch_manager import IngestionBatchManager
    bm = IngestionBatchManager()
    
    async def fake_crawl(max_pages, send_emails, progress_callback):
        for p in range(1, max_pages + 1):
            await progress_callback("cards_found", {
                "phase": "discovery",
                "page": p,
                "cards_count": 50
            })
            for i in range(48):
                await progress_callback("bdc_ingested", {
                    "phase": "bdc_item",
                    "processed_count": (p - 1) * 48 + i + 1,
                    "portal_id": 100000 + (p - 1) * 48 + i,
                    "line_items_count": 7
                })
    
    with patch("src.engine.batch_manager.run_active_crawl_cycle", side_effect=fake_crawl):
        record = await bm.execute_batch(pages=3, trigger_type="test")
        assert record.cards_scraped == 150
        assert record.tenders_ingested == 144
        assert record.line_items_extracted == 144 * 7


