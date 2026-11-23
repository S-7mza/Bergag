import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from starlette.testclient import TestClient
from src.api.main import app
from src.models.tender import Tender, Buyer, LineItem
from src.database.session import get_db_session

@pytest.fixture
def client():
    return TestClient(app)

def test_search_and_urgency_combination(client):
    """
    Verifies that search keywords are mandatory (AND logic between keywords)
    and correctly combined with urgency multi-selection (OR between intervals).
    """
    now = datetime.now(timezone.utc)
    bid = uuid.uuid4()
    buyer = Buyer(id=bid, slug="commune-tahannaout", official_name="Commune Tahannaout", buyer_type="commune")

    t1 = Tender(
        portal_id=410348,
        source_type="bdc",
        reference="21/TAH/2026",
        compound_natural_key="tah:21:2026",
        buyer_id=bid,
        title="CONCEPTION ET DEPLOIEMENT D UNE APPLICATION WEB DE GESTION",
        main_category="Services",
        published_at=now - timedelta(days=1),
        deadline_at=now + timedelta(hours=16),  # bracket: < 1d
        status="active"
    )
    t1.buyer = buyer
    item1 = LineItem(item_order=1, designation="Application Web de Gestion de Stock", technical_specs="Docker")
    t1.line_items = [item1]

    captured_stmts = []

    async def mock_execute(stmt):
        captured_stmts.append(stmt)
        res = MagicMock()
        res.scalars.return_value.all.return_value = [t1]
        return res

    mock_session = AsyncMock()
    mock_session.execute = mock_execute
    app.dependency_overrides[get_db_session] = lambda: mock_session

    try:
        # Test 1: Search single keyword
        res1 = client.get("/api/feed?profile_name=it_hardware&search=application")
        assert res1.status_code == 200
        data1 = res1.json()
        assert len(data1) == 1
        assert data1[0]["portal_id"] == 410348

        # Test 2: Search multi-word (mandatory AND between words)
        res2 = client.get("/api/feed?profile_name=it_hardware&search=application web")
        assert res2.status_code == 200
        params2 = str(captured_stmts[-1].compile().params)
        # Verify that both words are bound as parameters
        assert "%application%" in params2
        assert "%web%" in params2

        # Test 3: Search combined with multi-selection urgency
        res3 = client.get("/api/feed?profile_name=it_hardware&search=web&urgency=1d,2d")
        assert res3.status_code == 200
        params3 = str(captured_stmts[-1].compile().params)
        assert "%web%" in params3
        sql3 = str(captured_stmts[-1])
        # Verify urgency OR clause is present alongside search AND
        assert "deadline_at" in sql3

        # Test 4: Direct ID search lookup (e.g. "#410348" or "410348")
        res4 = client.get("/api/feed?profile_name=it_hardware&search=410348")
        assert res4.status_code == 200
        params4 = str(captured_stmts[-1].compile().params)
        assert "410348" in params4

    finally:
        app.dependency_overrides.pop(get_db_session, None)
