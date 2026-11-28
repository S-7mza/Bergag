from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.api.auth import create_session_token
from src.api.main import app
from src.api.routes.feed import _expand_search_word_variants
from src.engine.antigravity_study import AntigravityStudyManager, AntigravityStudyRecord, antigravity_study_manager
from src.engine.cps_extractor import CPSDeterministicExtractor
from src.engine.opportunity_xyz import OpportunityXYZEngine
from src.engine.scoring_cascade import ScoringCascadeEngine
from src.profiles.loader import load_profile


@pytest.fixture
def client():
    return TestClient(app)


def test_accent_insensitive_search_expansion():
    variants = _expand_search_word_variants("developpement")
    assert "developpement" in variants
    assert "développement" in variants
    assert "réseau" in _expand_search_word_variants("reseau")


def test_cps_deterministic_extractor():
    tender_data = {
        "portal_id": 999111,
        "title": "Conception et développement d'un portail web",
        "prestation_type": "Services informatiques",
        "line_items": [],
    }
    sample_cps = """
    Article 4 : Caution provisoire : 12 000 DH.
    Article 5 : Délai d'exécution : 90 jours à compter de l'ordre de service.
    Article 6 : Délai de garantie : 12 mois.
    Une visite des lieux obligatoire est prévue le 05/12/2026.
    Le prestataire doit disposer de la certification ISO 27001 et respecter la conformité CNDP.
    Livrables : Code source complet, documentation technique, formation des utilisateurs et maintenance applicative.
    Des pénalités de retard seront appliquées.
    """
    findings = CPSDeterministicExtractor.extract(tender_data, attachment_text=sample_cps)
    assert findings.has_attachment_text is True
    assert findings.caution_provisoire and "12 000 DH" in findings.caution_provisoire
    assert findings.execution_delay == "90 jours"
    assert findings.warranty_period == "12 mois"
    assert findings.site_visit_required is True
    assert "ISO 27001" in findings.certifications_required
    assert "Conformité CNDP (Loi 09-08)" in findings.certifications_required
    assert "Code source" in findings.deliverables
    assert "Maintenance / TMA" in findings.deliverables
    assert findings.penalties_mentioned is True


def test_opportunity_xyz_engine_and_drivers():
    now = datetime.now(timezone.utc)
    findings = CPSDeterministicExtractor.extract(
        {"title": "Portail Web", "line_items": []},
        attachment_text="Livrables : Code source et maintenance applicative.",
    )
    res = OpportunityXYZEngine.evaluate(
        tender_data={
            "portal_id": 999222,
            "source_type": "marche_public",
            "deadline_at": (now + timedelta(days=10)).isoformat(),
        },
        technical_fit_x=90.0,
        hardware_dependency="NONE",
        primary_domain="Développement Web & Portails",
        cps_findings=findings,
        buyer_spent_ytd_mad=150000.0,
        similar_awards_median_mad=280000.0,
        similar_awards_count=4,
        incumbent_share_pct=20.0,
    )
    assert res.priority_tier == "P1"
    assert res.opportunity_score >= 80.0
    assert res.commercial_value_y >= 80.0
    assert res.win_probability_z >= 80.0
    axes = {d.axis for d in res.attention_drivers}
    assert {"X", "Y", "Z"}.issubset(axes)


@pytest.mark.asyncio
async def test_scoring_cascade_empty_line_items_fallback_and_antigravity_override(tmp_path):
    profile = load_profile("software_data")
    engine = ScoringCascadeEngine()
    now = datetime.now(timezone.utc)
    tender_data = {
        "portal_id": 999333,
        "reference": "AO/WEB/2026",
        "source_type": "marche_public",
        "title": "Développement d'un portail web et API REST Python",
        "buyer_name": "Ministère Test",
        "main_category": "Services",
        "prestation_type": "Services informatiques",
        "execution_location": "Rabat-Salé-Kénitra",
        "deadline_at": (now + timedelta(days=8)).isoformat(),
        "status": "active",
        "line_items": [],
    }
    res = await engine.evaluate_tender(tender_data, profile)
    assert res.overall_score >= 50.0
    assert res.xyz_evaluation is not None
    assert res.xyz_evaluation["source"] == "engine"

    # Now save an Antigravity study and verify authoritative override
    orig_studies = dict(antigravity_study_manager._studies)
    try:
        antigravity_study_manager._studies[999333] = AntigravityStudyRecord(
            portal_id=999333,
            verdict="GO",
            priority_tier="P1",
            opportunity_score=94.0,
            technical_fit_x=96.0,
            commercial_value_y=90.0,
            win_probability_z=92.0,
            why_reasons=["X: Stack Python/React 100% maîtrisée", "Y: AO > 500k MAD", "Z: 8 jours de délai"],
            bid_strategy="Soumissionner en chef de file",
        )
        res_ag = await engine.evaluate_tender(tender_data, profile)
        assert res_ag.overall_score == 94.0
        assert res_ag.decision_recommendation == "GO"
        assert res_ag.xyz_evaluation["source"] == "antigravity"
        assert res_ag.antigravity_study is not None
    finally:
        antigravity_study_manager._studies = orig_studies


def test_antigravity_api_endpoints(client):
    admin_headers = {"Authorization": f"Bearer {create_session_token('admin@bergag.ma', 'admin')}"}
    viewer_headers = {"Authorization": f"Bearer {create_session_token('viewer@bergag.ma', 'viewer')}"}
    orig_studies = dict(antigravity_study_manager._studies)
    orig_path = antigravity_study_manager.ledger_path

    try:
        antigravity_study_manager.ledger_path = Path("data/test_ag_ledger_tmp.json")
        # Viewer cannot save study
        denied = client.post(
            "/api/agent/antigravity/study/999444",
            json={"verdict": "GO", "priority_tier": "P1", "opportunity_score": 88.0},
            headers=viewer_headers,
        )
        assert denied.status_code == 403

        # Admin saves study
        ok = client.post(
            "/api/agent/antigravity/study/999444",
            json={
                "verdict": "GO",
                "priority_tier": "P1",
                "opportunity_score": 89.0,
                "technical_fit_x": 92.0,
                "commercial_value_y": 85.0,
                "win_probability_z": 88.0,
                "why_reasons": ["X: Portail web sur mesure", "Y: Budget confortable"],
                "bid_strategy": "Mettre en avant les références web.",
            },
            headers=admin_headers,
        )
        assert ok.status_code == 200
        assert ok.json()["study"]["portal_id"] == 999444

        # Unauthenticated read of study is rejected (401)
        unauth = client.get("/api/agent/antigravity/study/999444")
        assert unauth.status_code == 401

        # Authenticated read of saved study succeeds
        got = client.get("/api/agent/antigravity/study/999444", headers=admin_headers)
        assert got.status_code == 200
        assert got.json()["verdict"] == "GO"

        # UI contains Batch Studio & injection-safe delimiter
        page = client.get("/")
        assert page.status_code == 200
        assert "exportAntigravityBatch" in page.text
        assert "applyAntigravityBatchJson" in page.text
        assert "<tender_cps_data>" in page.text
    finally:
        antigravity_study_manager._studies = orig_studies
        if Path("data/test_ag_ledger_tmp.json").exists():
            Path("data/test_ag_ledger_tmp.json").unlink()
        antigravity_study_manager.ledger_path = orig_path
