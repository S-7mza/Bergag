import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from src.engine.cancellation_tracker import (
    is_cancellation_notice,
    extract_target_cancelled_reference,
    reconcile_database_cancellations
)
from src.engine.scoring_cascade import ScoringCascadeEngine
from src.profiles.loader import load_profile
from src.models.tender import Tender, Buyer


def test_is_cancellation_notice_detection():
    # True positives
    assert is_cancellation_notice("DÉCISION D'ANNULATION DE L’AVIS D’ACHAT SUR BON DE COMMANDE N° : 1/2026", "7/2026") is True
    assert is_cancellation_notice("Décision d'annulation du bon de commande N°32-2026", "35-2026") is True
    assert is_cancellation_notice("Achat de fournitures diverses", "DA13-BC/2026") is True
    assert is_cancellation_notice("FOURNITURES DE MATÉRIEL (Annule et remplace Avis d'achat 30/2026)", "53/2026") is True
    assert is_cancellation_notice("Annulation de l'avis d'achat n °105/2026/ISTAHTT", "/105/2026/ISTAHTT") is True
    assert is_cancellation_notice("قرار إلغاء سند الطلب رقم 12/2026", "12/2026") is True

    # True negatives (normal actionable tenders)
    assert is_cancellation_notice("Achat de matériel informatique et ordinateurs portables", "BC/10/2026") is False
    assert is_cancellation_notice("Fourniture de logiciels et développement web", "AO/05/2026") is False
    assert is_cancellation_notice("Installation caméras de vidéosurveillance IP", "CCTV-2026-01") is False


def test_extract_target_cancelled_reference():
    # Exact extraction of referenced previous tender
    assert extract_target_cancelled_reference("DÉCISION D'ANNULATION DE L’AVIS D’ACHAT SUR BON DE COMMANDE N° : 1/2026", "7/2026") == "1/2026"
    assert extract_target_cancelled_reference("Décision d'annulation du bon de commande N°32-2026", "35-2026") == "32-2026"
    assert extract_target_cancelled_reference("Décision d'annulation d’avis d’achat sur bon de commande n° 13-BC/2026", "DA13-BC/2026") == "13-BC/2026"
    assert extract_target_cancelled_reference("FOURNITURES DE MATÉRIEL (Annule et remplace Avis d'achat 30/2026)", "53/2026") == "30/2026"
    assert extract_target_cancelled_reference("Annulation de l'avis d'achat n °105/2026/ISTAHTT", "/105/2026/ISTAHTT") == "105/2026/ISTAHTT"
    assert extract_target_cancelled_reference("Avis d'achat divers", "DA15-BC/2026") == "15-BC/2026"

    # Non-cancellation titles return None
    assert extract_target_cancelled_reference("Achat de matériel informatique pour la commune", "BC/10/2026") is None


@pytest.mark.asyncio
async def test_scoring_cascade_disqualifies_cancellation_notice():
    """Cancellation notice mentioning IT keywords must NOT score GO; must be ANNULÉ with 0 score"""
    cancellation_tender = {
        "portal_id": 351070,
        "reference": "DA13-BC/2026",
        "title": "Décision d'annulation d’avis d’achat sur bon de commande n° 13-BC/2026 relatif à l'achat de matériel informatique et ordinateurs portables",
        "buyer_name": "Ministère de la Justice",
        "execution_location": "Rabat",
        "main_category": "Fournitures",
        "published_at": "2026-11-20T10:00:00+01:00",
        "deadline_at": "2026-11-30T10:00:00+01:00",
        "status": "active",
        "line_items": [
            {
                "item_order": 1,
                "designation": "Ordinateur de bureau Core i7 16Go RAM",
                "technical_specs": "Windows 11 Pro",
                "unit": "U",
                "quantity": 10.0,
                "tva_rate": 20.0,
                "warranty_required": "1 an"
            }
        ]
    }

    profile = load_profile("it_hardware")
    engine = ScoringCascadeEngine()

    result = await engine.evaluate_tender(cancellation_tender, profile)

    assert result.decision_recommendation == "NO-GO"
    assert result.overall_score == 0.0
    assert "annulé" in result.llm_reasoning.lower() or "cancelled" in result.llm_reasoning.lower()
    assert "13-BC/2026" in result.llm_reasoning


@pytest.mark.asyncio
async def test_reconcile_database_cancellations_propagates_status():
    """Reconciling database cancellations marks notice as annule and propagates cancellation to previous tender"""
    buyer_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # 1. Original target tender (currently active in DB)
    t_target = Tender(
        portal_id=400001,
        source_type="bdc",
        reference="13-BC/2026",
        compound_natural_key=f"buyer:13-BC/2026:2026",
        buyer_id=buyer_id,
        title="Achat de matériel informatique et accessoires",
        main_category="Fournitures",
        published_at=now - timedelta(days=5),
        deadline_at=now + timedelta(days=2),
        status="active"
    )

    # 2. Subsequent cancellation notice published by the same buyer
    t_notice = Tender(
        portal_id=400050,
        source_type="bdc",
        reference="DA13-BC/2026",
        compound_natural_key=f"buyer:DA13-BC/2026:2026",
        buyer_id=buyer_id,
        title="Décision d'annulation d’avis d’achat sur bon de commande n° 13-BC/2026",
        main_category="Fournitures",
        published_at=now - timedelta(days=1),
        deadline_at=now + timedelta(days=5),
        status="active"
    )

    mock_session = AsyncMock()
    # Mock candidate search returning t_notice
    mock_candidates_res = MagicMock()
    mock_candidates_res.scalars.return_value.all.return_value = [t_notice]

    # Mock target search returning t_target
    mock_target_res = MagicMock()
    mock_target_res.scalars.return_value.all.return_value = [t_target]

    mock_session.execute.side_effect = [mock_candidates_res, mock_target_res]

    res = await reconcile_database_cancellations(mock_session)

    assert res["notices_tagged"] == 1
    assert res["targets_cancelled"] == 1
    assert t_notice.status == "annule"
    assert t_target.status == "annule"
    assert mock_session.commit.called is True
