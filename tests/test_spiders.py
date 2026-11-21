import pytest
from pathlib import Path
from unittest.mock import AsyncMock
from src.scraper.listing_spider import ListingSpider
from src.scraper.detail_spider import DetailSpider
from src.scraper.ingestion_service import slugify

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def test_slugify():
    assert slugify("Commune rurale de RDADNA O. MALEK") == "commune-rurale-de-rdadna-o-malek"
    assert slugify("Ministère de l'Équipement & de l'Eau") == "ministere-de-l-equipement-de-l-eau"
    assert slugify("   ") == "acheteur-inconnu"

@pytest.mark.asyncio
async def test_listing_spider_with_fixture():
    fixture_path = FIXTURES_DIR / "active_listing_page1.html"
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    mock_client = AsyncMock()
    mock_client.get.return_value = html

    spider = ListingSpider(client=mock_client)
    raw_log, cards = await spider.fetch_page(page=1, page_size=50)

    assert raw_log.page_type == "listing"
    assert raw_log.http_status == 200
    assert len(raw_log.content_hash) == 64  # SHA-256 length
    assert len(cards) == 10
    assert cards[0]["reference"] != ""

@pytest.mark.asyncio
async def test_detail_spider_with_fixture():
    fixture_path = FIXTURES_DIR / "detail_409807.html"
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    mock_client = AsyncMock()
    mock_client.get.return_value = html

    spider = DetailSpider(client=mock_client)
    raw_log, detail = await spider.fetch_detail(portal_id=409807)

    assert raw_log.page_type == "detail"
    assert raw_log.portal_id == 409807
    assert len(raw_log.content_hash) == 64
    assert detail["portal_id"] == 409807
    assert len(detail["line_items"]) == 7
    assert detail["line_items"][0]["quantity"] == 14.0

