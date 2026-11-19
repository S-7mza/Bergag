import pytest
from pathlib import Path
from unittest.mock import AsyncMock
from src.scraper.results_spider import ResultsSpider
from src.engine.award_matcher import clean_procurement_reference, compute_compound_ref_key

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def test_clean_procurement_reference():
    ref1, year1 = clean_procurement_reference("N° 06/2026")
    assert "06-2026" in ref1
    assert year1 == 2026

    ref2, year2 = clean_procurement_reference("35 / 2026")
    assert "35-2026" in ref2
    assert year2 == 2026

    ref3, year3 = clean_procurement_reference("178/FONC/2026/UIT")
    assert "178-fonc-2026-uit" in ref3
    assert year3 == 2026

def test_compute_compound_ref_key():
    key = compute_compound_ref_key("Commune rurale de SIROUA", "35/2026")
    assert key == "commune-rurale-de-siroua:35-2026:2026"

    key2 = compute_compound_ref_key("Commune rurale de RDADNA O. MALEK", "06/2026")
    assert key2 == "commune-rurale-de-rdadna-o-malek:06-2026:2026"

@pytest.mark.asyncio
async def test_results_spider_with_fixture():
    fixture_path = FIXTURES_DIR / "results_page1.html"
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    mock_client = AsyncMock()
    mock_client.get.return_value = html

    spider = ResultsSpider(client=mock_client)
    raw_log, awards = await spider.fetch_page(page=1)

    assert raw_log.page_type == "result"
    assert raw_log.http_status == 200
    assert len(raw_log.content_hash) == 64
    assert len(awards) == 10

    # Test parsed fields on first item
    item1 = awards[0]
    assert item1["reference"] != ""
    assert item1["buyer_name"] != ""
    assert item1["status"] in ["Attribué", "Infructueux"]

