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
    assert "Mes Dossiers" in response.text
    assert "Chiffrage & Devis" in response.text
    assert "Radar & Concurrence" in response.text
    assert "pipelineItems" in response.text

def test_pipeline_lifecycle(client):
    test_portal_id = 999123
    # 1. Shortlist tender
    shortlist_res = client.post("/api/actions", json={
        "profile_id": "00000000-0000-0000-0000-000000000000",
        "tender_id": test_portal_id,
        "action": "shortlisted",
        "bid_amount_mad": 85000.0,
        "user_notes": "Priorité commerciale Q4",
        "tender_metadata": {
            "reference": "BC/999/2026",
            "title": "Acquisition caméras IP et serveurs NVR",
            "buyer_name": "Commune de Rabat",
            "execution_location": "Rabat",
            "deadline_at": "30/11/2026 12:00",
            "match_score": 92.5
        }
    })
    assert shortlist_res.status_code == 200
    body = shortlist_res.json()
    assert body["success"] is True
    assert body["action"] == "shortlisted"
    assert body["tender_id"] == test_portal_id

    # 2. Retrieve pipeline
    get_res = client.get("/api/pipeline")
    assert get_res.status_code == 200
    items = get_res.json()
    matched = [i for i in items if i["portal_id"] == test_portal_id]
    assert len(matched) == 1
    assert matched[0]["action"] == "shortlisted"
    assert matched[0]["bid_amount_mad"] == 85000.0
    assert matched[0]["title"] == "Acquisition caméras IP et serveurs NVR"

    # 3. Transition to in_preparation (En chiffrage)
    prep_res = client.post("/api/actions", json={
        "profile_id": "00000000-0000-0000-0000-000000000000",
        "tender_id": test_portal_id,
        "action": "in_preparation",
        "bid_amount_mad": 92000.0
    })
    assert prep_res.status_code == 200
    assert prep_res.json()["action"] == "in_preparation"

    # 4. Filter pipeline by action
    filter_res = client.get("/api/pipeline?action=in_preparation")
    assert filter_res.status_code == 200
    prep_items = filter_res.json()
    assert any(i["portal_id"] == test_portal_id for i in prep_items)

    # 5. Remove from pipeline
    del_res = client.delete(f"/api/pipeline/{test_portal_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # 6. Verify removal
    after_res = client.get("/api/pipeline")
    after_items = after_res.json()
    assert not any(i["portal_id"] == test_portal_id for i in after_items)

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

def test_bcrypt_hashing_and_verification():
    from src.api.auth import hash_password, verify_password
    plain = "SecurePassword123!"
    hashed = hash_password(plain)
    assert hashed.startswith(("$2a$", "$2b$", "$2y$"))
    assert verify_password(plain, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False

def test_admin_create_user_and_authenticate(client):
    # Create new analyst user via Admin API
    new_user_data = {
        "email": "karim.tazi@bergag.ma",
        "username": "ktazi",
        "password": "KarimPassword2026!",
        "full_name": "Karim Tazi",
        "role": "analyst",
        "title": "Ingénieur Devis & Réponse AO",
        "avatar_color": "teal"
    }
    create_res = client.post("/api/auth/users", json=new_user_data)
    assert create_res.status_code == 201
    created = create_res.json()
    assert created["email"] == "karim.tazi@bergag.ma"
    assert created["role"] == "analyst"
    assert "tender:pricing_calculator" in created["permissions"]

    # Verify new user can log in with bcrypt verification
    login_res = client.post("/api/auth/login", json={
        "username_or_email": "ktazi",
        "password": "KarimPassword2026!"
    })
    assert login_res.status_code == 200
    token_data = login_res.json()
    assert "token" in token_data
    assert token_data["user"]["full_name"] == "Karim Tazi"

def test_list_team_users(client):
    res = client.get("/api/auth/users")
    assert res.status_code == 200
    users = res.json()
    assert len(users) >= 3
    emails = [u["email"] for u in users]
    assert "admin@bergag.ma" in emails

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
    from src.engine.batch_manager import batch_manager
    with patch("src.engine.batch_manager.run_active_crawl_cycle", new_callable=AsyncMock) as mock_crawl, \
         patch.object(batch_manager, "pending_backfill_queue", []):
        mock_crawl.return_value = None
        res = client.post("/api/admin/ingestion/remediate", json={"pages": 2})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "remediation_started"

def test_admin_batch_trigger(client):
    from src.engine.batch_manager import batch_manager
    with patch("src.engine.batch_manager.run_active_crawl_cycle", new_callable=AsyncMock) as mock_crawl, \
         patch.object(batch_manager, "pending_backfill_queue", []):
        mock_crawl.return_value = None
        # Test default and multi-page triggers (up to 37 pages for 100% active parity)
        res = client.post("/api/admin/ingestion/batches/trigger", json={"pages": 1})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "batch_started"

        res37 = client.post("/api/admin/ingestion/batches/trigger", json={"pages": 37, "send_emails": False})
        assert res37.status_code == 200
        assert res37.json()["status"] == "batch_started"


def test_admin_historical_batch_trigger(client):
    from src.engine.batch_manager import batch_manager
    with patch("src.engine.batch_manager.run_historical_crawl_cycle", new_callable=AsyncMock) as mock_hist_crawl, \
         patch.object(batch_manager, "pending_backfill_queue", []):
        mock_hist_crawl.return_value = None
        res = client.post("/api/admin/ingestion/batches/trigger-historical", json={
            "start_date": "10/11/2026",
            "end_date": "17/11/2026",
            "period_mode": "range",
            "pages": 15,
            "send_emails": False
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "historical_batch_started"
        assert "10/11/2026" in data["message"]


@pytest.mark.asyncio
async def test_batch_manager_cards_accumulation():
    from src.engine.batch_manager import IngestionBatchManager
    bm = IngestionBatchManager()
    bm.pending_backfill_queue = []
    
    async def fake_crawl(max_pages, send_emails, progress_callback, **kwargs):
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


def test_admin_abort_batch_endpoint(client):
    from src.engine.batch_manager import batch_manager, IngestionBatchRecord
    from datetime import datetime

    # Set an active batch
    active = IngestionBatchRecord(
        batch_id="BATCH-TEST-ABORT",
        trigger_type="manual",
        status="in_progress",
        started_at=datetime.now(),
        pages_requested=2
    )
    batch_manager.active_batch = active
    batch_manager.batches.append(active)

    res = client.post("/api/admin/ingestion/batches/abort")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "aborted"
    assert data["batch_id"] == "BATCH-TEST-ABORT"
    assert batch_manager.active_batch.status == "aborted"

    # Reset
    batch_manager.active_batch = None
    batch_manager._abort_requested = False


def test_batch_manager_bdc_range_formatting():
    from src.engine.batch_manager import IngestionBatchRecord
    from datetime import datetime

    rec = IngestionBatchRecord(
        batch_id="BATCH-TEST-RANGE",
        trigger_type="manual",
        status="completed",
        started_at=datetime.now(),
        first_bdc_id=410218,
        last_bdc_id=410170
    )
    d = rec.to_dict()
    assert d["first_bdc_id"] == 410170
    assert d["last_bdc_id"] == 410218
    assert d["bdc_range"] == "#410170 → #410218"


def test_audit_active_tenders_endpoint(client):
    res = client.get("/api/admin/ingestion/audit-active")
    assert res.status_code == 200
    data = res.json()
    assert "is_fully_covered" in data
    assert "portal_total_active" in data
    assert "db_total_active" in data
    assert "coverage_pct" in data
    assert "missing_count" in data
    assert "all_active_items" in data


def test_reconcile_active_tenders_endpoint(client):
    res = client.post("/api/admin/ingestion/audit-active/reconcile", json={"portal_ids": []})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("reconciled", "noop")
    assert "message" in data


@pytest.mark.asyncio
async def test_audit_active_coverage_logic():
    from src.engine.batch_manager import IngestionBatchManager
    from unittest.mock import AsyncMock, patch

    bm = IngestionBatchManager()

    mock_cards = [
        {"portal_id": 999001, "reference": "REF-001", "title": "Fourniture IT", "buyer_name": "Acheteur A", "deadline_raw": "25/11/2026 12:00", "deadline_at": "2026-11-25T12:00:00+01:00", "status": "active"},
        {"portal_id": 999002, "reference": "REF-002", "title": "Maintenance Réseau", "buyer_name": "Acheteur B", "deadline_raw": "26/11/2026 14:00", "deadline_at": "2026-11-26T14:00:00+01:00", "status": "active"}
    ]

    mock_spider = AsyncMock()
    mock_spider.fetch_active.return_value = (None, mock_cards, 2)

    with patch("src.engine.batch_manager.ListingSpider", return_value=mock_spider), \
         patch("src.engine.batch_manager.PortalHttpClient"):
        result = await bm.audit_active_tenders_coverage(force_refresh=True)
        assert result["portal_total_active"] >= 2
        assert len(result["all_active_items"]) >= 2
        assert "coverage_pct" in result
        assert "is_fully_covered" in result




