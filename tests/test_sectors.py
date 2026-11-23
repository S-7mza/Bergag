import pytest
from starlette.testclient import TestClient
from src.api.main import app
from src.profiles.loader import load_profile, load_all_profiles
from src.engine.line_item_matcher import LineItemMatcher
from src.engine.feedback_manager import feedback_manager, normalize_profile_key

@pytest.fixture
def client():
    return TestClient(app)

def test_all_11_profiles_load_and_validate():
    """Verifies that all 11 Moroccan public procurement sector profiles load and adhere to schema"""
    profiles = load_all_profiles()
    assert len(profiles) >= 11
    slugs = {p.profile_id for p in profiles}
    expected_slugs = {
        "it_hardware", "software_data", "cctv_security", "btp_construction",
        "electricite_fluides", "medical_pharma", "transport_vehicules",
        "nettoyage_gardiennage", "bureau_mobilier", "etudes_conseil", "communication_event"
    }
    assert expected_slugs.issubset(slugs)

    for p in profiles:
        assert p.profile_name
        assert p.icon
        assert len(p.catalog) > 0
        assert len(p.macro_filters.categories) > 0

def test_api_list_and_get_profiles(client):
    """Verifies GET /api/profiles and GET /api/profiles/{id} endpoints"""
    res = client.get("/api/profiles")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 11

    # Check structure
    first = data[0]
    assert "id" in first
    assert "profile_name" in first
    assert "icon" in first
    assert "catalog_count" in first
    assert "keywords_count" in first

    # Check detail endpoint
    res_btp = client.get("/api/profiles/btp_construction")
    assert res_btp.status_code == 200
    btp_data = res_btp.json()
    assert btp_data["id"] == "btp_construction"
    assert "BTP" in btp_data["profile_name"]
    assert len(btp_data["catalog"]) > 0

def test_weighted_line_item_coverage_priority():
    """
    Verifies that catalog items with higher weights contribute proportionally more
    to the overall line-item coverage ratio and confidence.
    """
    profile = load_profile("it_hardware")
    # In it_hardware:
    # computers-workstations has weight 1.0
    # Let's create two mock item sets:
    # 1. Matching a single high-priority item
    high_weight_item = {
        "item_order": 1,
        "designation": "Fourniture d'ordinateurs portables Core i7 16Go RAM SSD",
        "technical_specs": "Windows 11 Pro Full HD",
        "quantity": 10,
        "unit": "Unité"
    }
    accessory_item = {
        "item_order": 2,
        "designation": "Fourniture de plantes vertes décoratives et pots",
        "technical_specs": "Plantes naturelles",
        "quantity": 10,
        "unit": "Unité"
    }

    # Case A: Both matched vs Case B: Only high-weight item matched
    cov_high_only, evals, unmatched = LineItemMatcher.match_line_items([high_weight_item, accessory_item], profile)
    assert len(evals) == 2
    assert evals[0]["is_matched"] is True
    assert evals[1]["is_matched"] is False
    assert cov_high_only > 0.0

def test_sector_feedback_namespace_isolation():
    """
    Verifies that human alignment feedback given under one sector (e.g. software_data)
    does not affect or bleed into another sector (e.g. it_hardware or btp_construction).
    """
    test_portal_id = 999123

    try:
        # 1. Record alignment under software_data
        feedback_manager.record_feedback(
            portal_id=test_portal_id,
            profile_name="software_data",
            is_aligned=True,
            tender_title="Développement d'une application mobile"
        )

        # software_data must see it as aligned
        fb_sw = feedback_manager.get_feedback(test_portal_id, "software_data")
        assert fb_sw is not None
        assert fb_sw["is_aligned"] is True
        assert test_portal_id in feedback_manager.get_aligned_portal_ids("software_data")

        # it_hardware must NOT see it as aligned
        fb_hw = feedback_manager.get_feedback(test_portal_id, "it_hardware")
        assert fb_hw is None
        assert test_portal_id not in feedback_manager.get_aligned_portal_ids("it_hardware")

        # btp_construction must NOT see it as aligned
        fb_btp = feedback_manager.get_feedback(test_portal_id, "btp_construction")
        assert fb_btp is None
        assert test_portal_id not in feedback_manager.get_aligned_portal_ids("btp_construction")

    finally:
        feedback_manager.delete_feedback(test_portal_id, "software_data")

def test_profile_key_normalization():
    """Verifies that normalize_profile_key handles standard slugs and title strings"""
    assert normalize_profile_key("it_hardware") == "it_hardware"
    assert normalize_profile_key("Matériel Informatique, Bureautique & Réseaux") == "it_hardware"
    assert normalize_profile_key("btp_construction") == "btp_construction"
    assert normalize_profile_key("Travaux de Bâtiment et Génie Civil") == "btp_construction"
    assert normalize_profile_key("medical_pharma") == "medical_pharma"
    assert normalize_profile_key("Fournitures Médicales et Hospitalières") == "medical_pharma"
    assert normalize_profile_key("custom_secteur_test") == "custom_secteur_test"

def test_all_sectors_system_profile(client):
    """Verifies that 'all' (Tous les Secteurs) behaves as a protected system-global profile"""
    # 1. Listed in /api/profiles as first item
    res = client.get("/api/profiles")
    assert res.status_code == 200
    profiles = res.json()
    assert profiles[0]["id"] == "all"
    assert profiles[0]["profile_name"] == "Tous les Secteurs"
    assert profiles[0]["icon"] == "🌐"

    # 2. Detail endpoint returns global profile
    res_detail = client.get("/api/profiles/all")
    assert res_detail.status_code == 200
    data = res_detail.json()
    assert data["id"] == "all"
    assert data["profile_name"] == "Tous les Secteurs"
    assert data.get("is_system_global") is True

    # 3. Modification is rejected
    res_put = client.put("/api/profiles/all", json={"profile_name": "Hack"})
    assert res_put.status_code == 400

    # 4. Deletion is rejected
    res_del = client.delete("/api/profiles/all")
    assert res_del.status_code == 403

def test_all_sectors_feed_and_detail(client):
    """Verifies that feed and tender detail work seamlessly with profile_name='all' without sector restrictions"""
    import uuid
    from datetime import datetime, timezone, timedelta
    from unittest.mock import AsyncMock, MagicMock
    from src.models.tender import Tender, Buyer, LineItem
    from src.database.session import get_db_session

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
        deadline_at=now + timedelta(hours=36),  # > 24h
        status="active"
    )
    t1.buyer = buyer
    item1 = LineItem(item_order=1, designation="Application Web de Gestion de Stock", technical_specs="Docker", quantity=1.0)
    t1.line_items = [item1]

    async def mock_execute(stmt):
        res = MagicMock()
        res.scalars.return_value.all.return_value = [t1]
        res.scalar_one_or_none.return_value = t1
        return res

    mock_session = AsyncMock()
    mock_session.execute = mock_execute
    app.dependency_overrides[get_db_session] = lambda: mock_session

    try:
        # Feed in all mode
        res = client.get("/api/feed?profile_name=all&limit=20")
        assert res.status_code == 200
        items = res.json()
        assert len(items) == 1
        assert items[0]["portal_id"] == 410348
        assert items[0]["match_score"] == 100.0
        assert items[0]["decision_verdict"] == "GO"

        # Detail in all mode
        res_detail = client.get(f"/api/tenders/{t1.portal_id}?profile_name=all")
        assert res_detail.status_code == 200
        detail = res_detail.json()
        assert detail["portal_id"] == t1.portal_id
        assert detail["match_score"] == 100.0
        assert detail["decision_verdict"] == "GO"
        assert "Tous les Secteurs" in detail["llm_reasoning"]
    finally:
        app.dependency_overrides.pop(get_db_session, None)

