import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.testclient import TestClient

from src.api.main import app
from src.engine.active_learning import ActiveLearningTuner
from src.profiles.loader import load_profile


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def isolated_tuner(tmp_path):
    """Creates an ActiveLearningTuner instance with an isolated temporary ledger file."""
    with patch("src.engine.active_learning.TUNER_LEDGER_FILE", tmp_path / "tuner_ledger.json"), \
         patch("src.engine.active_learning.feedback_manager") as mock_fm:
        mock_fm.record_feedback = MagicMock()
        mock_fm.delete_feedback = MagicMock()
        tuner = ActiveLearningTuner()
        yield tuner


@pytest.mark.asyncio
async def test_active_learning_sampling_prioritizes_uncertainty_and_probes(isolated_tuner):
    profile = load_profile("special_ai_hybrid")

    # Seed a pending confirmation probe for "consommables"
    session = isolated_tuner.get_session("special_ai_hybrid")
    session["pending_probes"].append({
        "source_portal_id": 1001,
        "target_feature": "consommables",
        "feature_type": "keyword",
    })

    candidates = [
        {
            "portal_id": 2001,
            "reference": "01/2026",
            "title": "Achat de denrées alimentaires et boissons",
            "buyer_name": "Commune A",
            "main_category": "Fournitures",
            "status": "active",
            "line_items": [],
        },
        {
            "portal_id": 2002,
            "reference": "02/2026",
            "title": "Fourniture de consommables informatiques et cartouches",
            "buyer_name": "Commune B",
            "main_category": "Fournitures",
            "status": "active",
            "line_items": [{"designation": "Cartouche toner", "quantity": 10, "unit": "U"}],
        },
        {
            "portal_id": 2003,
            "reference": "03/2026",
            "title": "Développement d'une plateforme web et portail cloud",
            "buyer_name": "Ministère C",
            "main_category": "Services",
            "status": "closed",
            "is_closed": True,
            "line_items": [{"designation": "Développement portail web React", "quantity": 1, "unit": "Forfait"}],
        },
    ]

    selected = await isolated_tuner.select_next_candidates(candidates, profile, limit=3)
    assert len(selected) == 3
    # Probe candidate (2002) should be prioritized first
    assert selected[0]["portal_id"] == 2002
    assert selected[0]["sampling_strategy"] == "confirmation_probe"


def test_swipe_gradient_update_confirmation_and_undo(isolated_tuner):
    tender_positive = {
        "portal_id": 3001,
        "title": "Développement application mobile et portail cloud",
        "buyer_name": "Agence Digitale",
        "main_category": "Services",
        "line_items": [{"designation": "API Backend Python FastAPI", "quantity": 1, "unit": "Forfait"}],
    }

    # 1. Swipe Right (Accept)
    res_acc = isolated_tuner.record_swipe(
        portal_id=3001,
        profile_id="special_ai_hybrid",
        decision="accept",
        tender_data=tender_positive,
        score_before=55.0,
    )
    assert res_acc["status"] == "recorded"
    assert res_acc["needs_confirmation"] is False
    assert res_acc["metrics"]["accepted_count"] == 1

    # Verify positive token weight increased
    stats = isolated_tuner.get_stats("special_ai_hybrid")
    pos_terms = {item["term"]: item["weight"] for item in stats["top_positive_keywords"]}
    assert any(k in pos_terms for k in ("application", "mobile", "portail", "cloud", "fastapi"))

    # 2. Swipe Left (Reject) on borderline/high score tender -> triggers confirmation probe
    tender_borderline = {
        "portal_id": 3002,
        "title": "Fourniture de cartouches et consommables informatiques",
        "buyer_name": "Commune X",
        "main_category": "Fournitures",
        "line_items": [{"designation": "Cartouches encre laser", "quantity": 20, "unit": "U"}],
    }
    res_rej = isolated_tuner.record_swipe(
        portal_id=3002,
        profile_id="special_ai_hybrid",
        decision="reject",
        tender_data=tender_borderline,
        score_before=62.0,
        sampling_strategy="uncertainty_boundary",
    )
    assert res_rej["needs_confirmation"] is True
    assert len(res_rej["confirmation_options"]) >= 2

    # 3. Confirm exclusion rule
    conf_res = isolated_tuner.confirm_rejection_rule(
        profile_id="special_ai_hybrid",
        rule_type="keyword",
        rule_value="cartouches",
        portal_id=3002,
    )
    assert "cartouches" in conf_res["exclusion_keywords"]
    assert conf_res["metrics"]["confirmed_rules_count"] == 1

    # 4. Undo last swipe (3002)
    undo_res = isolated_tuner.undo_last_swipe("special_ai_hybrid")
    assert undo_res["status"] == "undone"
    assert undo_res["undone_portal_id"] == 3002
    assert 3002 not in isolated_tuner.get_swiped_ids("special_ai_hybrid")


def test_save_logic_to_profile_yaml(isolated_tuner, tmp_path):
    import shutil
    from src.profiles.loader import PROFILES_DIR

    # Copy special_ai_hybrid.yaml into tmp_path so we never mutate real YAML in unit tests
    temp_profiles = tmp_path / "configs"
    temp_profiles.mkdir()
    shutil.copy(PROFILES_DIR / "special_ai_hybrid.yaml", temp_profiles / "special_ai_hybrid.yaml")

    session = isolated_tuner.get_session("special_ai_hybrid")
    session["feature_weights"]["keyword_weights"]["kubernetes_custom"] = 0.65
    session["feature_weights"]["exclusion_keywords"].append("plomberie_sanitaire_test")

    with patch("src.engine.active_learning.PROFILES_DIR", temp_profiles):
        save_res = isolated_tuner.save_logic_to_profile("special_ai_hybrid")
        assert save_res["status"] == "saved"
        assert "kubernetes_custom" in save_res["added_positives"]
        assert "plomberie_sanitaire_test" in save_res["added_exclusions"]


def test_tuner_api_routes(client):
    with patch("src.api.routes.tuner.active_tuner") as mock_tuner:
        mock_tuner.get_stats.return_value = {
            "profile_id": "special_ai_hybrid",
            "metrics": {"total_swipes": 5, "accepted_count": 3, "rejected_count": 2},
            "top_positive_keywords": [],
            "top_negative_keywords": [],
            "exclusion_keywords": [],
        }
        mock_tuner.confirm_rejection_rule.return_value = {
            "status": "confirmed",
            "message": "OK",
            "metrics": {},
            "exclusion_keywords": ["papier"],
        }
        mock_tuner.undo_last_swipe.return_value = {"status": "undone", "undone_portal_id": 101}
        mock_tuner.save_logic_to_profile.return_value = {"status": "saved", "message": "Saved!"}

        res_stats = client.get("/api/tuner/stats?profile_id=special_ai_hybrid")
        assert res_stats.status_code == 200
        assert res_stats.json()["metrics"]["total_swipes"] == 5

        res_conf = client.post(
            "/api/tuner/confirm-rule",
            json={"profile_id": "special_ai_hybrid", "rule_type": "keyword", "rule_value": "papier"},
        )
        assert res_conf.status_code == 200
        assert "papier" in res_conf.json()["exclusion_keywords"]

        res_undo = client.post("/api/tuner/undo", json={"profile_id": "special_ai_hybrid"})
        assert res_undo.status_code == 200
        assert res_undo.json()["status"] == "undone"

        res_save = client.post("/api/tuner/save-logic", json={"profile_id": "special_ai_hybrid"})
        assert res_save.status_code == 200
        assert res_save.json()["status"] == "saved"
