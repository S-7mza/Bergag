import pytest
from pathlib import Path
from src.scraper.parser import parse_detail_page
from src.profiles.loader import load_profile
from src.engine.scoring_cascade import ScoringCascadeEngine
from src.alerts.email_dispatcher import (
    render_decision_card_html, 
    render_decision_card_text, 
    EmailDispatcher
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def cctv_tender_data():
    fixture_path = FIXTURES_DIR / "detail_409807.html"
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()
    return parse_detail_page(html, portal_id=409807)

@pytest.mark.asyncio
async def test_email_decision_card_rendering_and_dispatch(cctv_tender_data):
    profile = load_profile("cctv_security")
    engine = ScoringCascadeEngine()

    result = await engine.evaluate_tender(cctv_tender_data, profile)

    # 1. Test HTML rendering
    html = render_decision_card_html(cctv_tender_data, result, profile)
    assert "#409807" in html
    assert "06/2026" in html
    assert "Commune rurale de RDADNA O. MALEK" in html
    assert "https://www.marchespublics.gov.ma/bdc/entreprise/consultation/show/409807" in html
    assert "RECOMMENDED GO" in html
    assert "HIKVISION" in html

    # 2. Test Text rendering
    text = render_decision_card_text(cctv_tender_data, result, profile)
    assert "DECISION CARD" in text
    assert "409807" in text
    assert "RECOMMENDED GO" in text

    # 3. Test Async Dispatcher
    dispatcher = EmailDispatcher()
    success = await dispatcher.send_decision_card(cctv_tender_data, result, profile)
    assert success is True

