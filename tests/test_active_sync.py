import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from src.scraper.parser import parse_date, parse_listing_page
from src.engine.batch_manager import IngestionBatchManager
from src.scraper.listing_spider import ListingSpider

def test_french_date_parsing():
    assert parse_date("16 mars 2027 à 14:00") == "2027-03-16T14:00:00+01:00"
    assert parse_date("31 déc. 2026 à 12:00") == "2026-12-31T12:00:00+01:00"
    assert parse_date("03 déc. 2026 à 16:00") == "2026-12-03T16:00:00+01:00"
    assert parse_date("30 nov. 2026 à 14:00") == "2026-11-30T14:00:00+01:00"
    assert parse_date("27/11/2026 14:00") == "2026-11-27T14:00:00+01:00"
    assert parse_date("18/11/2026 16:15") == "2026-11-18T16:15:00+01:00"
    assert parse_date("") is None

def test_listing_card_deadline_and_status():
    html_card = """
    <article class="bdc-card bdc-card--lien">
        <div class="bdc-card__side bdc-card__side--ko">
            <span class="bdc-card__k">Clôture</span>
            <span class="bdc-card__v">16 mars 2027</span>
            <span class="bdc-card__s">à 14:00</span>
        </div>
        <div class="bdc-card__body">
            <div class="bdc-card__tags">
                <span class="bdc-card__ref">REF-100</span>
                <span class="badge bg-danger">Annulé</span>
            </div>
            <a class="bdc-card__title" href="/bdc/entreprise/consultation/show/400100">Fourniture Matériel</a>
            <div class="bdc-card__meta">
                <span>Commune Test</span>
                <span>Rabat</span>
            </div>
        </div>
    </article>
    """
    cards = parse_listing_page(html_card)
    assert len(cards) == 1
    c = cards[0]
    assert c["portal_id"] == 400100
    assert c["status"] == "annule"
    assert c["deadline_raw"] == "16 mars 2027 à 14:00"
    assert c["deadline_at"] == "2027-03-16T14:00:00+01:00"

@pytest.mark.asyncio
async def test_fetch_all_active_cards():
    mock_client = AsyncMock()
    spider = ListingSpider(mock_client)

    # Mock fetch_active to return 120 total results across 3 pages
    async def mock_fetch_active(page=1, page_size=50):
        if page == 1:
            cards = [{"portal_id": i} for i in range(1, 51)]
        elif page == 2:
            cards = [{"portal_id": i} for i in range(51, 101)]
        else:
            cards = [{"portal_id": i} for i in range(101, 121)]
        return None, cards, 120

    spider.fetch_active = AsyncMock(side_effect=mock_fetch_active)

    total_cnt, all_cards = await spider.fetch_all_active_cards(max_pages=10, concurrency=2)
    assert total_cnt == 120
    assert len(all_cards) == 120
    assert all_cards[0]["portal_id"] == 1
    assert all_cards[-1]["portal_id"] == 120

@pytest.mark.asyncio
async def test_audit_active_deep_scan():
    bm = IngestionBatchManager()
    mock_spider = AsyncMock()

    mock_all_cards = [
        {"portal_id": 999100, "reference": "R1", "title": "T1", "buyer_name": "B1", "status": "active", "deadline_at": "2027-01-01T12:00:00+01:00", "deadline_raw": "01 janv. 2027 12:00"},
        {"portal_id": 999101, "reference": "R2", "title": "T2", "buyer_name": "B2", "status": "active", "deadline_at": "2027-01-02T12:00:00+01:00", "deadline_raw": "02 janv. 2027 12:00"},
        {"portal_id": 999102, "reference": "R3", "title": "T3", "buyer_name": "B3", "status": "active", "deadline_at": "2027-01-03T12:00:00+01:00", "deadline_raw": "03 janv. 2027 12:00"}
    ]
    mock_spider.fetch_all_active_cards.return_value = (3, mock_all_cards)

    with patch("src.engine.batch_manager.ListingSpider", return_value=mock_spider), \
         patch("src.engine.batch_manager.PortalHttpClient"):
        audit_res = await bm.audit_active_tenders_coverage(force_refresh=True, deep_scan=True)
        assert audit_res["portal_total_active"] == 3
        assert audit_res["immediate_missing_count"] >= 0
        assert "missing_portal_ids" in audit_res

@pytest.mark.asyncio
async def test_execute_active_sync_batch():
    bm = IngestionBatchManager()
    bm.active_batch = None

    mock_spider = AsyncMock()
    mock_cards = [
        {"portal_id": 888001, "reference": "SYNC-01", "title": "Avis 1", "buyer_name": "Acheteur 1", "status": "active"},
        {"portal_id": 888002, "reference": "SYNC-02", "title": "Avis 2", "buyer_name": "Acheteur 2", "status": "active"}
    ]
    mock_spider.fetch_all_active_cards.return_value = (2, mock_cards)

    mock_detail_spider = AsyncMock()
    mock_detail_spider.fetch_detail.return_value = (
        None,
        {
            "portal_id": 888001,
            "reference": "SYNC-01",
            "title": "Avis 1",
            "buyer_name": "Acheteur 1",
            "main_category": "Fournitures",
            "published_at": "2026-11-20T10:00:00+01:00",
            "deadline_at": "2027-02-01T12:00:00+01:00",
            "line_items": []
        }
    )

    mock_service = AsyncMock()
    mock_service.detail_spider = mock_detail_spider
    mock_service.ingest_tender_detail = AsyncMock(return_value=MagicMock())

    mock_session = AsyncMock()
    mock_exec_res = MagicMock()
    mock_exec_res.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_exec_res)
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__.return_value = mock_session
    mock_factory.return_value.__aexit__.return_value = False

    mock_client = AsyncMock()
    mock_client.close = AsyncMock()

    with patch("src.engine.batch_manager.ListingSpider", return_value=mock_spider), \
         patch("src.engine.batch_manager.PortalHttpClient", return_value=mock_client), \
         patch("src.ingestion.bdc.service.BdcIngestionService", return_value=mock_service), \
         patch("src.scraper.ingestion_service.IngestionService", return_value=mock_service), \
         patch("src.engine.batch_manager.async_session_factory", mock_factory), \
         patch.object(bm, "_save_batch_to_db", new=AsyncMock()):
        
        record = await bm.execute_active_sync_batch(user_name="Tester", target_portal_ids=[888001, 888002])
        assert record.status == "completed"
        assert record.progress_pct == 100
        assert record.tenders_ingested == 2
        assert bm.active_batch is None

from starlette.testclient import TestClient
from src.api.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_sync_all_active_route(client):
    from unittest.mock import patch, AsyncMock
    with patch("src.api.routes.batches.batch_manager.execute_active_sync_batch", new=AsyncMock()), \
         patch("src.api.routes.batches.batch_manager.active_batch", None):
        response = client.post("/api/admin/ingestion/audit-active/sync-all", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sync_started"
