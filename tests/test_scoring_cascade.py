import pytest
from pathlib import Path
from src.scraper.parser import parse_detail_page
from src.profiles.loader import load_profile
from src.engine.scoring_cascade import ScoringCascadeEngine

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def cctv_tender_data():
    fixture_path = FIXTURES_DIR / "detail_409807.html"
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()
    return parse_detail_page(html, portal_id=409807)

@pytest.mark.asyncio
async def test_cctv_profile_against_cctv_tender_high_match(cctv_tender_data):
    """
    Tender #409807 is an active CCTV supply & installation BDC.
    When evaluated against the CCTV profile, it must produce >= 85% score and GO verdict.
    """
    cctv_profile = load_profile("cctv_security")
    engine = ScoringCascadeEngine()

    result = await engine.evaluate_tender(cctv_tender_data, cctv_profile)

    assert result.decision_recommendation == "GO"
    assert result.overall_score >= 85.0
    assert result.coverage_score == 100.0  # 100% of line items matched to CCTV catalog
    assert len(result.line_item_matches) == 7
    assert all(item["is_matched"] for item in result.line_item_matches)

@pytest.mark.asyncio
async def test_software_profile_against_cctv_tender_rejected(cctv_tender_data):
    """
    When the same CCTV tender #409807 is evaluated against Hamza's Software/Data profile,
    it must be rejected with a NO-GO verdict and low score.
    """
    software_profile = load_profile("software_data")
    engine = ScoringCascadeEngine()

    result = await engine.evaluate_tender(cctv_tender_data, software_profile)

    assert result.decision_recommendation == "NO-GO"
    assert result.overall_score <= 25.0
    assert result.coverage_score == 0.0  # Zero software line items

@pytest.mark.asyncio
async def test_cancelled_tender_hard_filter_rejection(cctv_tender_data):
    """Cancelled tenders must be dropped at Stage 1 with 0 score"""
    cctv_tender_data["status"] = "annule"
    cctv_profile = load_profile("cctv_security")
    engine = ScoringCascadeEngine()

    result = await engine.evaluate_tender(cctv_tender_data, cctv_profile)

    assert result.decision_recommendation == "NO-GO"
    assert result.overall_score == 0.0
    assert "cancelled" in result.llm_reasoning.lower()

@pytest.mark.asyncio
async def test_negative_keyword_veto():
    """Tenders containing negative constraint keywords must be vetoed at Stage 2"""
    cctv_profile = load_profile("cctv_security")
    engine = ScoringCascadeEngine()

    # Create a tender with allowed category but negative constraint keyword (gardiennage)
    tender = {
        "portal_id": 999999,
        "title": "Fourniture de gardiennage et sécurité humaine des locaux",
        "main_category": "Fournitures",
        "prestation_type": "Gardiennage",
        "status": "active",
        "deadline_at": "2026-12-01T14:00:00+01:00",
        "line_items": [
            {"item_order": 1, "designation": "Agents de gardiennage 24/7", "quantity": 4, "unit": "Agent"}
        ]
    }

    result = await engine.evaluate_tender(tender, cctv_profile)

    assert result.decision_recommendation == "NO-GO"
    assert result.overall_score == 0.0
    assert "veto" in result.llm_reasoning.lower()
