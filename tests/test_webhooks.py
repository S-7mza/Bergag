import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.scraper.parser import parse_detail_page
from src.profiles.loader import load_profile
from src.engine.scoring_cascade import ScoringCascadeEngine
from src.alerts.webhook_dispatcher import WebhookDispatcher, build_webhook_payload

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def cctv_tender_data():
    fixture_path = FIXTURES_DIR / "detail_409807.html"
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()
    return parse_detail_page(html, portal_id=409807)

@pytest.mark.asyncio
async def test_webhook_payload_structure(cctv_tender_data):
    profile = load_profile("cctv_security")
    engine = ScoringCascadeEngine()
    result = await engine.evaluate_tender(cctv_tender_data, profile)

    payload = build_webhook_payload(cctv_tender_data, result, profile)

    # 1. Base Event Schema
    assert payload["event"] == "high_fit_tender_detected"
    assert payload["tender"]["portal_id"] == 409807
    assert payload["tender"]["reference"] == "06/2026"
    assert payload["tender"]["buyer_name"] == "Commune rurale de RDADNA O. MALEK"
    assert payload["tender"]["line_item_count"] > 0
    assert payload["evaluation"]["verdict"] == "GO"
    assert payload["evaluation"]["overall_score"] >= 80.0
    assert payload["profile"]["profile_name"] == profile.profile_name

    # 2. Deep Links
    assert "#tender=409807" in payload["links"]["fiche_url"]
    assert "https://www.marchespublics.gov.ma" in payload["links"]["portal_url"]

    # 3. Formatted Markdown for chat channels
    assert "*[OPPORTUNITÉ BDC #409807]" in payload["formatted_text"]
    assert "Commune rurale de RDADNA O. MALEK" in payload["formatted_text"]

    # 4. Slack Blocks
    assert len(payload["slack"]["blocks"]) >= 3
    header_block = payload["slack"]["blocks"][0]
    assert header_block["type"] == "header"
    assert "BDC #409807" in header_block["text"]["text"]
    actions_block = payload["slack"]["blocks"][-1]
    assert actions_block["type"] == "actions"
    assert any("Fiche 60s" in el["text"]["text"] for el in actions_block["elements"])

    # 5. Microsoft Teams Card
    assert payload["teams"]["@type"] == "MessageCard"
    assert payload["teams"]["themeColor"] == "059669"
    assert len(payload["teams"]["sections"]) > 0
    facts = payload["teams"]["sections"][0]["facts"]
    assert any(f["name"] == "Acheteur:" for f in facts)

@pytest.mark.asyncio
async def test_webhook_mock_dispatch_when_unconfigured(cctv_tender_data):
    profile = load_profile("cctv_security")
    engine = ScoringCascadeEngine()
    result = await engine.evaluate_tender(cctv_tender_data, profile)

    dispatcher = WebhookDispatcher(default_webhook_url=None)
    # When no webhook URL is passed, dispatcher logs and returns True (resilient fallback)
    success = await dispatcher.send_notification(cctv_tender_data, result, profile)
    assert success is True

@pytest.mark.asyncio
async def test_webhook_http_dispatch_mocked(cctv_tender_data):
    profile = load_profile("cctv_security")
    engine = ScoringCascadeEngine()
    result = await engine.evaluate_tender(cctv_tender_data, profile)

    dispatcher = WebhookDispatcher(default_webhook_url="https://hooks.slack.com/services/TEST/TOKEN")

    # Mock HTTP 200 Success
    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200

    with patch("httpx.AsyncClient.post", return_value=mock_resp_200):
        ok = await dispatcher.send_notification(cctv_tender_data, result, profile)
        assert ok is True

    # Mock HTTP 500 Error
    mock_resp_500 = MagicMock()
    mock_resp_500.status_code = 500
    mock_resp_500.text = "Internal Server Error"

    with patch("httpx.AsyncClient.post", return_value=mock_resp_500):
        fail = await dispatcher.send_notification(cctv_tender_data, result, profile)
        assert fail is False
