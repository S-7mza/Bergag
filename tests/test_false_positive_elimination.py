import pytest
from datetime import datetime, timezone, timedelta
from src.profiles.loader import load_profile
from src.engine.scoring_cascade import ScoringCascadeEngine
from src.engine.feedback_manager import feedback_manager, extract_tokens
from src.engine.hard_filters import evaluate_hard_filters
from src.api.routes.feed import extract_profile_candidate_keywords

@pytest.mark.asyncio
async def test_truck_tender_is_disqualified_for_software_profile():
    profile = load_profile("software_data")
    scoring_engine = ScoringCascadeEngine()

    future_deadline = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()

    # Exact replica of BDC #411883
    truck_tender = {
        "portal_id": 411883,
        "reference": "26/2026",
        "title": "Achat d’un camion au compte de la commune imgdal",
        "main_category": "Fournitures",
        "prestation_type": "Achat de matériel de transport, de citernes et d’engins",
        "execution_location": "AL HAOUZ",
        "deadline_at": future_deadline,
        "status": "active",
        "line_items": [
            {
                "item_order": 1,
                "designation": "Motorisation et transmission • Moteur. Bloc ISUZU JE493ZLQ4 à 4 cylindres en ligne",
                "technical_specs": "poste radio et témoins d'alerte de pression d'air et d'huile au tableau de bord. Châssis, freins, pneus 7.00R16",
                "quantity": 1,
                "unit": "Unité"
            }
        ]
    }

    # 1. Test Hard Filter catches incompatible prestation
    is_eligible, hard_reasons = evaluate_hard_filters(truck_tender, profile)
    assert not is_eligible
    assert any("incompatible" in r.lower() for r in hard_reasons)

    # 2. Test Scoring Engine instantly returns NO-GO with 0% score
    res = await scoring_engine.evaluate_tender(truck_tender, profile)
    assert res.decision_recommendation == "NO-GO"
    assert res.overall_score == 0.0

@pytest.mark.asyncio
async def test_commune_is_never_extracted_as_active_learning_keyword():
    # Even if title mentions 'commune', extract_tokens must ignore administrative words
    text = "Achat de logiciels pour la commune de Benslimane et la province"
    tokens = extract_tokens(text)
    assert "commune" not in tokens
    assert "province" not in tokens
    assert "logiciels" in tokens or "logiciel" in tokens

@pytest.mark.asyncio
async def test_candidate_keywords_do_not_contain_administrative_stopwords():
    profile = load_profile("software_data")
    kws = extract_profile_candidate_keywords(profile)
    assert "commune" not in kws
    assert "achat" not in kws
    assert "maroc" not in kws
    assert "materiel" not in kws
