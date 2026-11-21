import pytest
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from src.api.main import app
from src.models.tender import Award, Tender, Buyer
from src.scraper.results_spider import ResultsSpider
from src.ingestion.awards.matcher import AwardMatcher, compute_compound_ref_key, clean_procurement_reference
from src.ingestion.awards.service import AwardsIngestionService
from src.ingestion.awards.auditor import AwardsAuditor
from src.ingestion.batches.manager import AwardsBatchManager

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def client():
    return TestClient(app)

def test_clean_procurement_reference_normalization():
    ref, year = clean_procurement_reference("N° 06/2026")
    assert ref == "06-2026"
    assert year == 2026

    ref2, year2 = clean_procurement_reference("178/FONC/2026/UIT")
    assert ref2 == "178-fonc-2026-uit"
    assert year2 == 2026

    compound = compute_compound_ref_key("Commune Urbaine de Casablanca", "N° 06/2026")
    assert compound == "commune-urbaine-de-casablanca:06-2026:2026"

@pytest.mark.asyncio
async def test_results_spider_fetch_results_with_fixture():
    fixture_path = FIXTURES_DIR / "results_page1.html"
    assert fixture_path.exists(), "Results fixture must exist"

    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    mock_client = AsyncMock()
    mock_client.get.return_value = html

    spider = ResultsSpider(client=mock_client)
    raw_log, awards, total_archive = await spider.fetch_results(page=1, page_size=50)

    assert raw_log.page_type == "result"
    assert len(awards) == 10
    assert total_archive == 339934

    first = awards[0]
    assert first["reference"] == "178/FONC/2026/UIT"
    assert first["winner_name"] == "L'ATELIER DU VOYAGE"
    assert first["amount_ttc"] == 10040.0
    assert first["devis_received_count"] == 6

@pytest.mark.asyncio
async def test_awards_ingestion_service_create_new():
    mock_session = AsyncMock()
    
    # 1. Buyer check -> None (creates new)
    buyer_res = MagicMock()
    buyer_res.scalar_one_or_none.return_value = None
    
    # 2. Award check -> None (creates new)
    award_res = MagicMock()
    award_res.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [buyer_res, award_res]

    service = AwardsIngestionService(mock_session)
    # Stub matcher to return None
    service.matcher.find_matching_tender = AsyncMock(return_value=None)

    award_data = {
        "reference": "21/BI/2026/MRK",
        "title": "Achat fournitures de nettoyage",
        "buyer_name": "CRRA MARRAKECH",
        "winner_name": "SORNECH",
        "amount_ttc": 36946.80,
        "devis_received_count": 4,
        "status": "Attribué",
        "published_at": "2026-11-19T15:22:00+01:00"
    }

    award = await service.ingest_award(award_data)

    assert award.reference == "21/BI/2026/MRK"
    assert award.winner_name == "SORNECH"
    assert award.amount_ttc == Decimal("36946.80")
    assert award.devis_received_count == 4
    assert award.status == "Attribué"
    assert "crra-marrakech" in award.compound_ref_key
    assert mock_session.add.called
    assert mock_session.flush.called

@pytest.mark.asyncio
async def test_awards_ingestion_service_idempotent_update():
    mock_session = AsyncMock()

    # 1. Buyer exists
    mock_buyer = MagicMock(spec=Buyer, slug="crra-marrakech")
    buyer_res = MagicMock()
    buyer_res.scalar_one_or_none.return_value = mock_buyer

    # 2. Award already exists
    existing_award = MagicMock(spec=Award)
    existing_award.compound_ref_key = "crra-marrakech:21-bi-2026-mrk:2026"
    existing_award.winner_name = "SORNECH"
    existing_award.tender_id = None
    award_res = MagicMock()
    award_res.scalar_one_or_none.return_value = existing_award

    mock_session.execute.side_effect = [buyer_res, award_res]

    service = AwardsIngestionService(mock_session)
    service.matcher.find_matching_tender = AsyncMock(return_value=None)

    award_data = {
        "reference": "21/BI/2026/MRK",
        "title": "Achat fournitures de nettoyage",
        "buyer_name": "CRRA MARRAKECH",
        "winner_name": "SORNECH",
        "amount_ttc": 36946.80,
        "devis_received_count": 4,
        "status": "Attribué"
    }

    award = await service.ingest_award(award_data)

    assert award == existing_award
    assert existing_award.amount_ttc == Decimal("36946.80")
    assert existing_award.devis_received_count == 4

@pytest.mark.asyncio
async def test_awards_ingestion_tender_linking_and_status_update():
    mock_session = AsyncMock()

    # Buyer exists
    mock_buyer = MagicMock(spec=Buyer, slug="commune-marrakech")
    buyer_res = MagicMock()
    buyer_res.scalar_one_or_none.return_value = mock_buyer

    # Tender exists for Pass 1 matching
    tender_id_res = MagicMock()
    tender_id_res.scalar_one_or_none.return_value = 409807

    # Existing award check -> None
    award_res = MagicMock()
    award_res.scalar_one_or_none.return_value = None

    # Tender model retrieval for status update
    mock_tender = MagicMock(spec=Tender, portal_id=409807, status="active")
    tender_model_res = MagicMock()
    tender_model_res.scalar_one_or_none.return_value = mock_tender

    mock_session.execute.side_effect = [buyer_res, tender_id_res, award_res, tender_model_res]

    service = AwardsIngestionService(mock_session)

    award_data = {
        "reference": "06/2026",
        "title": "Installation de vidéosurveillance",
        "buyer_name": "Commune Marrakech",
        "winner_name": "SECURITAS MAROC",
        "amount_ttc": 285000.0,
        "devis_received_count": 5,
        "status": "Attribué"
    }

    award = await service.ingest_award(award_data)

    assert award.tender_id == 409807
    assert mock_tender.status == "attribue"

@pytest.mark.asyncio
async def test_awards_auditor_empty_db():
    mock_session = AsyncMock()
    count_res = MagicMock()
    count_res.scalar.return_value = 0
    mock_session.execute.return_value = count_res

    auditor = AwardsAuditor(mock_session)
    stats = await auditor.get_stats()

    assert stats["total_awards"] == 0
    assert stats["is_fallback_active"] is True
    assert "Simulation" in stats["status_label"]

@pytest.mark.asyncio
async def test_awards_auditor_populated_db():
    mock_session = AsyncMock()
    
    # 1. Total count
    r1 = MagicMock()
    r1.scalar.return_value = 50

    # 2. Status breakdown
    row_attribue = MagicMock(status="Attribué", count=42, sum_amount=15400000.0, avg_amount=366666.6, avg_devis=3.4)
    row_infruct = MagicMock(status="Infructueux", count=8, sum_amount=0.0, avg_amount=0.0, avg_devis=0.0)
    r2 = MagicMock()
    r2.all.return_value = [row_attribue, row_infruct]

    # 3. Linked count
    r3 = MagicMock()
    r3.scalar.return_value = 15

    # 4. Unique winners
    r4 = MagicMock()
    r4.scalar.return_value = 28

    # 5. Unique buyers
    r5 = MagicMock()
    r5.scalar.return_value = 18

    # 6. Max published_at
    r6 = MagicMock()
    r6.scalar.return_value = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)

    mock_session.execute.side_effect = [r1, r2, r3, r4, r5, r6]

    auditor = AwardsAuditor(mock_session)
    stats = await auditor.get_stats()

    assert stats["total_awards"] == 50
    assert stats["total_awarded"] == 42
    assert stats["total_infructueux"] == 8
    assert stats["total_awarded_mad"] == 15400000.0
    assert stats["linked_tenders_count"] == 15
    assert stats["linkage_rate_pct"] == 30.0
    assert stats["unique_winners_count"] == 28
    assert stats["is_fallback_active"] is False

def test_awards_api_endpoints(client):
    # Test GET stats
    with patch("src.ingestion.awards.auditor.AwardsAuditor.get_stats") as mock_stats:
        mock_stats.return_value = {
            "total_awards": 120,
            "total_awarded": 100,
            "total_infructueux": 20,
            "total_awarded_mad": 42000000.0,
            "avg_contract_mad": 420000.0,
            "avg_competition_density": 3.1,
            "linked_tenders_count": 35,
            "linkage_rate_pct": 29.2,
            "unique_winners_count": 45,
            "unique_buyers_count": 30,
            "latest_award_date": "20/11/2026 15:00",
            "is_fallback_active": False,
            "status_label": "Données Réelles en direct",
            "status_badge_class": "bg-emerald-500/10 text-emerald-400"
        }
        res_stats = client.get("/api/admin/ingestion/awards/stats")
        assert res_stats.status_code == 200
        data = res_stats.json()
        assert data["total_awards"] == 120
        assert data["is_fallback_active"] is False

    # Test GET state
    res_state = client.get("/api/admin/ingestion/awards/state")
    assert res_state.status_code == 200
    state = res_state.json()
    assert "is_running" in state
    assert "history" in state

    # Test POST sync trigger
    with patch("src.ingestion.batches.manager.AwardsBatchManager.execute_sync", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = {"status": "completed"}
        res_sync = client.post("/api/admin/ingestion/awards/sync", json={"pages": 3, "page_size": 50})
        assert res_sync.status_code == 200
        assert res_sync.json()["status"] == "sync_started"

    # Test POST abort
    res_abort = client.post("/api/admin/ingestion/awards/abort")
    assert res_abort.status_code == 200
    assert "status" in res_abort.json()
