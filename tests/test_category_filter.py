import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from src.api.main import app
from src.database.session import get_db_session
from src.models.tender import Tender, Buyer

@pytest.fixture
def client():
    return TestClient(app)

def test_category_filters_sql_and_routing(client):
    now = datetime.now(timezone.utc)
    
    # 1. Tender Fournitures (Matériel)
    t_mat = Tender(
        portal_id=777001,
        source_type="bdc",
        reference="BC/777/001",
        compound_natural_key="buyer:ref:2026-mat",
        buyer_id=uuid.uuid4(),
        title="Fourniture d'ordinateurs portables et serveurs",
        main_category="Fournitures",
        published_at=now,
        deadline_at=now + timedelta(days=5),
        status="active"
    )
    t_mat.buyer = Buyer(slug="buyer-mat", official_name="Direction IT", buyer_type="ministère")
    t_mat.line_items = []

    # 2. Tender Services
    t_serv = Tender(
        portal_id=777002,
        source_type="bdc",
        reference="BC/777/002",
        compound_natural_key="buyer:ref:2026-serv",
        buyer_id=uuid.uuid4(),
        title="Prestations de maintenance et support des serveurs",
        main_category="Services",
        published_at=now,
        deadline_at=now + timedelta(days=5),
        status="active"
    )
    t_serv.buyer = Buyer(slug="buyer-serv", official_name="Direction IT", buyer_type="ministère")
    t_serv.line_items = []

    captured_stmts = []

    mock_session = AsyncMock()
    async def mock_execute(stmt):
        captured_stmts.append(stmt)
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [t_mat, t_serv]
        return mock_res

    mock_session.execute = mock_execute

    app.dependency_overrides[get_db_session] = lambda: mock_session

    try:
        # Test 1: Category = both
        res_both = client.get("/api/feed?category=both&limit=50")
        assert res_both.status_code == 200
        last_stmt = captured_stmts[-1]
        stmt_both_str = str(last_stmt).lower()
        # In SQLAlchemy 2.0, in_() renders as tenders.main_category in (__[postcompile_main_category_1])
        assert "tenders.main_category in" in stmt_both_str
        compiled = last_stmt.compile()
        params_values = list(compiled.params.values())
        assert any("fournitures" in str(v).lower() for v in params_values) or any("fournitures" in str(v).lower() for v in [compiled.params.get("main_category_1_1"), compiled.params.get("main_category_1_2")])

        # Test 2: Category = Fournitures (Matériel seul)
        res_mat = client.get("/api/feed?category=Fournitures&limit=50")
        assert res_mat.status_code == 200
        stmt_mat = captured_stmts[-1]
        params_mat = stmt_mat.compile().params
        assert any("fourniture" in str(v).lower() for v in params_mat.values())

        # Test 3: Category = Services (Services seuls)
        res_serv = client.get("/api/feed?category=Services&limit=50")
        assert res_serv.status_code == 200
        stmt_serv = captured_stmts[-1]
        params_serv = stmt_serv.compile().params
        assert any("service" in str(v).lower() for v in params_serv.values())

        # Test 4: Alias 'materiel'
        res_alias = client.get("/api/feed?category=materiel&limit=50")
        assert res_alias.status_code == 200
        stmt_alias = captured_stmts[-1]
        params_alias = stmt_alias.compile().params
        assert any("materiel" in str(v).lower() or "fourniture" in str(v).lower() for v in params_alias.values())

    finally:
        app.dependency_overrides.pop(get_db_session, None)
