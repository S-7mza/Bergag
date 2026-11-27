import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from starlette.testclient import TestClient
from src.api.main import app
from src.models.tender import Tender, Buyer, LineItem
from src.database.session import get_db_session
from src.profiles.loader import load_profile
from src.engine.scoring_cascade import ScoringCascadeEngine

@pytest.fixture
def client():
    return TestClient(app)

@pytest.mark.asyncio
async def test_hybrid_profile_loading():
    """Verifies that special_ai_hybrid profile loads with hybrid mode and weights"""
    profile = load_profile("special_ai_hybrid")
    assert profile.profile_id == "special_ai_hybrid"
    assert profile.scoring_mode == "hybrid"
    assert profile.scoring_weights.ai_engine_weight == 0.50
    assert profile.scoring_weights.cascade_weight == 0.50
    assert profile.scoring_weights.enable_hardware_damping is True
    assert len(profile.catalog) >= 5

@pytest.mark.asyncio
async def test_hybrid_scoring_pure_software_tender():
    """
    Verifies that a pure Web & Python development tender gets a high unified score (GO / >80%),
    combining AI diagnostic + sector cascade catalog coverage with no hardware penalty.
    """
    engine = ScoringCascadeEngine()
    profile = load_profile("special_ai_hybrid")

    now = datetime.now(timezone.utc)
    tender_data = {
        "portal_id": 99901,
        "reference": "WEB-DEV/2026",
        "title": "Développement et mise en place d'une plateforme web et portail avec React et Python",
        "buyer_name": "Ministère de la Transition Numérique",
        "prestation_type": "Services informatiques et développement logiciel",
        "main_category": "Services",
        "execution_location": "Rabat",
        "published_at": now.isoformat(),
        "deadline_at": (now + timedelta(days=10)).isoformat(),
        "status": "active",
        "line_items": [
            {
                "item_order": 1,
                "designation": "Conception et développement portail web React et Next.js",
                "technical_specs": "Frontend responsive, API REST, UI/UX",
                "quantity": 1.0,
                "unit": "Forfait"
            },
            {
                "item_order": 2,
                "designation": "Backend API REST et microservices en Python FastAPI",
                "technical_specs": "Python 3.12, PostgreSQL, Docker, Sécurité applicative",
                "quantity": 1.0,
                "unit": "Forfait"
            }
        ]
    }

    result = await engine.evaluate_tender(tender_data, profile)
    assert result.decision_recommendation == "GO"
    assert result.overall_score >= 80.0
    assert result.ai_matching_rate is not None
    assert result.ai_matching_rate >= 70.0
    assert result.hardware_dependency in ("NONE", "LOW")
    assert "Moteur Hybride Unifié" in result.llm_reasoning

@pytest.mark.asyncio
async def test_hybrid_scoring_hardware_dilution_damping():
    """
    Verifies that an offer containing 90% hardware (laptops, printers, toners)
    with only a token mention of 'installation logicielle' gets effectively damped
    down by the hardware dilution engine, preventing false-positive GOs.
    """
    engine = ScoringCascadeEngine()
    profile = load_profile("special_ai_hybrid")

    now = datetime.now(timezone.utc)
    tender_data = {
        "portal_id": 99902,
        "reference": "HW-SUPPLY/2026",
        "title": "Achat d'ordinateurs portables, imprimantes multifonctions et consommables avec configuration logicielle",
        "buyer_name": "Commune Rurale",
        "prestation_type": "Achat de matériel technique, de logiciels et de matériel informatique",
        "main_category": "Fournitures",
        "execution_location": "Settat",
        "published_at": now.isoformat(),
        "deadline_at": (now + timedelta(days=8)).isoformat(),
        "status": "active",
        "line_items": [
            {
                "item_order": 1,
                "designation": "Ordinateurs portables Core i7 avec Windows",
                "technical_specs": "32 GB RAM, 1TB SSD",
                "quantity": 20.0,
                "unit": "U"
            },
            {
                "item_order": 2,
                "designation": "Imprimantes laser réseau et toners",
                "technical_specs": "Consommables d'impression",
                "quantity": 10.0,
                "unit": "U"
            },
            {
                "item_order": 3,
                "designation": "Armoire de brassage et câblage RJ45",
                "technical_specs": "Câblage réseau cuivre",
                "quantity": 1.0,
                "unit": "Lot"
            }
        ]
    }

    result = await engine.evaluate_tender(tender_data, profile)
    # The heavy physical hardware must trigger dilution damping and prevent GO
    assert result.decision_recommendation in ("CONSIDER", "NO-GO")
    assert result.overall_score < 60.0
    assert result.hardware_dependency == "HIGH"
    assert any("matériel" in f.lower() for f in result.red_flags)

def test_feed_api_with_special_ai_hybrid(client):
    """Verifies that the /api/feed endpoint executes flawlessly when querying special_ai_hybrid profile"""
    now = datetime.now(timezone.utc)
    buyer = Buyer(slug="min-num", official_name="Ministère Numérique", buyer_type="ministere")

    t1 = Tender(
        portal_id=77701,
        source_type="bdc",
        reference="NUM/77701/2026",
        compound_natural_key="min:77701:2026",
        title="Plateforme Web et Application Mobile React Native",
        main_category="Services",
        published_at=now - timedelta(days=1),
        deadline_at=now + timedelta(hours=72),
        status="active"
    )
    t1.buyer = buyer
    t1.line_items = [
        LineItem(item_order=1, designation="Développement Web React", technical_specs="Docker Python API")
    ]

    async def mock_execute(stmt):
        res = MagicMock()
        res.scalars.return_value.all.return_value = [t1]
        return res

    mock_session = AsyncMock()
    mock_session.execute = mock_execute
    app.dependency_overrides[get_db_session] = lambda: mock_session

    try:
        res = client.get("/api/feed?profile_name=special_ai_hybrid&status_filter=all")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        item = data[0]
        assert item["portal_id"] == 77701
        assert item["match_score"] > 50.0
        assert item["decision_verdict"] in ("GO", "CONSIDER")
    finally:
        app.dependency_overrides.pop(get_db_session, None)
