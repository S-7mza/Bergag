import pytest
from src.engine.feedback_manager import AlignmentFeedbackManager
from src.engine.scoring_cascade import ScoringCascadeEngine
from src.profiles.loader import load_profile

def test_feedback_manager_record_and_active_learning():
    mgr = AlignmentFeedbackManager()
    
    # 1. Record positive feedback for a tender with specific terms
    res = mgr.record_feedback(
        portal_id=999111,
        profile_name="test_software",
        is_aligned=True,
        user_name="Hamza",
        user_notes="Développement Symfony PostgreSQL parfait",
        tender_title="Développement d'une application web Symfony",
        line_items_text="Prestation de développement Symfony et base PostgreSQL"
    )
    assert res["is_aligned"] is True
    assert "symfony" in res["learned_terms"]
    assert "postgresql" in res["learned_terms"]

    # 2. Check that active learning adjustment gives a positive bonus to a tender with learned terms
    delta, hits = mgr.calculate_active_learning_adjustment(
        "Refonte portail Symfony et administration",
        "test_software"
    )
    assert delta > 0.0
    assert "symfony" in hits

    # 3. Clean up
    mgr.delete_feedback(999111, "test_software")
    assert mgr.get_feedback(999111, "test_software") is None

@pytest.mark.asyncio
async def test_scoring_cascade_with_human_feedback():
    from datetime import datetime, timezone, timedelta
    from src.engine.feedback_manager import feedback_manager
    from src.engine.scoring_cascade import invalidate_tender_cache

    engine = ScoringCascadeEngine()
    profile = load_profile("software_data")
    now = datetime.now(timezone.utc)

    tender_data = {
        "portal_id": 999222,
        "title": "Développement et maintenance d'un portail web",
        "reference": "TEST/999/2026",
        "status": "active",
        "prestation_type": "Services informatiques",
        "execution_location": "Casablanca",
        "published_at": (now - timedelta(days=1)).isoformat(),
        "deadline_at": (now + timedelta(days=5)).isoformat(),
        "line_items": [
            {
                "item_order": 1,
                "designation": "Développement modules Python et API REST",
                "technical_specs": "Python FastAPI",
                "unit": "Jours",
                "quantity": 10.0,
                "tva_rate": 20.0,
                "warranty_required": None
            }
        ]
    }

    # Ensure clean slate before test
    feedback_manager.delete_feedback(999222, "software_data")
    invalidate_tender_cache(999222, "software_data")

    # Baseline scoring without human feedback
    base_res = await engine.evaluate_tender(tender_data, profile)
    assert base_res.alignment_feedback is None

    # Apply positive alignment confirmation
    feedback_manager.record_feedback(
        portal_id=999222,
        profile_name="software_data",
        is_aligned=True,
        user_name="Expert",
        tender_title=tender_data["title"],
        line_items_text="Développement modules Python et API REST"
    )
    invalidate_tender_cache(999222, "software_data")
    boosted_res = await engine.evaluate_tender(tender_data, profile)
    
    assert boosted_res.alignment_feedback == "aligned"
    assert boosted_res.overall_score >= 88.0
    assert boosted_res.decision_recommendation == "GO"
    assert "Alignement confirmé" in boosted_res.llm_reasoning

    # Apply negative rejection (marked out of scope / false positive)
    feedback_manager.record_feedback(
        portal_id=999222,
        profile_name="software_data",
        is_aligned=False,
        user_name="Expert",
        user_notes="Hors scope car compétence requise non disponible"
    )
    invalidate_tender_cache(999222, "software_data")
    demoted_res = await engine.evaluate_tender(tender_data, profile)

    assert demoted_res.alignment_feedback == "misaligned"
    assert demoted_res.overall_score <= 20.0
    assert demoted_res.decision_recommendation == "NO-GO"
    assert "Signalé hors secteur" in demoted_res.llm_reasoning

    # Clean up test feedback
    feedback_manager.delete_feedback(999222, "software_data")
    invalidate_tender_cache(999222, "software_data")
