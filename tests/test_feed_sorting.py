import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.testclient import TestClient
from src.api.main import app
from src.models.tender import Tender, Buyer, LineItem
from src.database.session import get_db_session
from src.engine.ai_diagnostician import AIMatchingDiagnosis

@pytest.fixture
def client():
    return TestClient(app)

def test_feed_sorting_options(client):
    """
    Verifies that the /api/feed endpoint correctly handles sorting:
    - ai_score_desc (Top AI score first)
    - ai_score_asc (Lowest AI score first)
    - score_desc (Highest rule/cascade match score first)
    - score_asc (Lowest rule/cascade match score first)
    - deadline_asc (Earliest deadline first)
    - items_desc (Most items first)
    - id_desc (Highest portal_id first)
    """
    now = datetime.now(timezone.utc)
    buyer = Buyer(slug="commune-test", official_name="Commune Test", buyer_type="commune")

    t1 = Tender(
        portal_id=101,
        source_type="bdc",
        reference="101/2026",
        compound_natural_key="comm:101:2026",
        title="Consultation Web et Python",
        main_category="Services",
        published_at=now - timedelta(days=2),
        deadline_at=now + timedelta(hours=10),
        status="active"
    )
    t1.buyer = buyer
    t1.line_items = [LineItem(item_order=1, designation="Item 1")]

    t2 = Tender(
        portal_id=102,
        source_type="bdc",
        reference="102/2026",
        compound_natural_key="comm:102:2026",
        title="Fourniture de Papeterie et Stylos",
        main_category="Fournitures",
        published_at=now - timedelta(days=1),
        deadline_at=now + timedelta(hours=48),
        status="active"
    )
    t2.buyer = buyer
    t2.line_items = [LineItem(item_order=1, designation="Item 1"), LineItem(item_order=2, designation="Item 2"), LineItem(item_order=3, designation="Item 3")]

    async def mock_execute(stmt):
        res = MagicMock()
        res.scalars.return_value.all.return_value = [t1, t2]
        return res

    mock_session = AsyncMock()
    mock_session.execute = mock_execute
    app.dependency_overrides[get_db_session] = lambda: mock_session

    diag_101 = AIMatchingDiagnosis(
        matching_rate=92.0,
        rating_label="EXCELLENT_MATCH",
        verdict="GO",
        confidence=95.0,
        primary_domain="Web & Data",
        sub_scores={"web": 90.0},
        detected_technologies=["Python"],
        deliverability_feasibility="HIGH",
        hardware_dependency="NONE",
        red_flags_and_gaps=[],
        strategic_recommendation="Go",
        diagnostic_summary="Top match",
        evaluated_at=str(now)
    )

    diag_102 = AIMatchingDiagnosis(
        matching_rate=5.0,
        rating_label="MISMATCH",
        verdict="NO-GO",
        confidence=98.0,
        primary_domain="Papeterie",
        sub_scores={},
        detected_technologies=[],
        deliverability_feasibility="LOW",
        hardware_dependency="HIGH",
        red_flags_and_gaps=[],
        strategic_recommendation="No-Go",
        diagnostic_summary="Mismatch",
        evaluated_at=str(now)
    )

    def mock_get_diag(pid):
        if pid == 101:
            return diag_101
        return diag_102

    try:
        with patch("src.api.routes.feed.ai_matching_agent.get_cached_diagnosis", side_effect=mock_get_diag):
            # 1. Sort by ai_score_desc -> t1 (92%) must be first!
            res_ai_desc = client.get("/api/feed?sort_by=ai_score_desc&status_filter=all")
            assert res_ai_desc.status_code == 200
            data_ai_desc = res_ai_desc.json()
            assert len(data_ai_desc) == 2
            assert data_ai_desc[0]["portal_id"] == 101
            assert data_ai_desc[0]["ai_matching"]["matching_rate"] == 92.0
            assert data_ai_desc[1]["portal_id"] == 102
            assert data_ai_desc[1]["ai_matching"]["matching_rate"] == 5.0

            # 2. Sort by ai_score_asc -> t2 (5%) must be first!
            res_ai_asc = client.get("/api/feed?sort_by=ai_score_asc&status_filter=all")
            assert res_ai_asc.status_code == 200
            data_ai_asc = res_ai_asc.json()
            assert data_ai_asc[0]["portal_id"] == 102
            assert data_ai_asc[1]["portal_id"] == 101

            # 3. Sort by items_desc -> t2 (3 items) must be first!
            res_items_desc = client.get("/api/feed?sort_by=items_desc&status_filter=all")
            assert res_items_desc.status_code == 200
            data_items = res_items_desc.json()
            assert data_items[0]["portal_id"] == 102
            assert data_items[0]["line_item_count"] == 3

            # 4. Sort by items_asc -> t1 (1 item) must be first!
            res_items_asc = client.get("/api/feed?sort_by=items_asc&status_filter=all")
            assert res_items_asc.status_code == 200
            data_items_asc = res_items_asc.json()
            assert data_items_asc[0]["portal_id"] == 101
            assert data_items_asc[0]["line_item_count"] == 1

            # 5. Sort by deadline_asc -> t1 (+10h) must be first!
            res_deadline = client.get("/api/feed?sort_by=deadline_asc&status_filter=all")
            assert res_deadline.status_code == 200
            data_deadline = res_deadline.json()
            assert data_deadline[0]["portal_id"] == 101

            # 6. Sort by deadline_desc -> t2 (+48h) must be first!
            res_deadline_desc = client.get("/api/feed?sort_by=deadline_desc&status_filter=all")
            assert res_deadline_desc.status_code == 200
            data_deadline_desc = res_deadline_desc.json()
            assert data_deadline_desc[0]["portal_id"] == 102

            # 7. Sort by id_desc -> t2 (102) must be first!
            res_id_desc = client.get("/api/feed?sort_by=id_desc&status_filter=all")
            assert res_id_desc.status_code == 200
            data_id_desc = res_id_desc.json()
            assert data_id_desc[0]["portal_id"] == 102

            # 8. Sort by id_asc -> t1 (101) must be first!
            res_id_asc = client.get("/api/feed?sort_by=id_asc&status_filter=all")
            assert res_id_asc.status_code == 200
            data_id_asc = res_id_asc.json()
            assert data_id_asc[0]["portal_id"] == 101

    finally:
        app.dependency_overrides.pop(get_db_session, None)
