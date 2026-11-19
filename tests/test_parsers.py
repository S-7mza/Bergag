import pytest
from pathlib import Path
from src.scraper.parser import parse_listing_page, parse_detail_page, parse_results_page

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def test_parse_active_listing_fixture():
    fixture_path = FIXTURES_DIR / "active_listing_page1.html"
    assert fixture_path.exists(), "Listing fixture must exist"
    
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    results = parse_listing_page(html)
    assert len(results) > 0, "Should parse at least 1 notice"
    assert len(results) == 10, "Default fixture has 10 cards"

    first = results[0]
    assert first["reference"] != "", "Reference should not be empty"
    assert first["title"] != "", "Title should not be empty"
    assert first["buyer_name"] != "", "Buyer name should not be empty"
    assert first["status"] in ["active", "annule"]

def test_parse_detail_fixture_409807():
    fixture_path = FIXTURES_DIR / "detail_409807.html"
    assert fixture_path.exists(), "Detail fixture must exist"

    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    detail = parse_detail_page(html, portal_id=409807)
    assert detail["portal_id"] == 409807
    assert detail["reference"] == "06/2026"
    assert "Commune rurale de RDADNA O. MALEK" in detail["buyer_name"]
    assert detail["main_category"] == "Travaux"
    assert "BENSLIMANE" in detail["execution_location"]
    assert detail["attachment_available"] is True
    assert "/download/409807/55593536" in detail["attachment_url"]

    # Verify line items
    items = detail["line_items"]
    assert len(items) == 7, "CCTV notice #409807 must have exactly 7 line items"
    
    # Check Camera item
    item1 = items[0]
    assert item1["item_order"] == 1
    assert "HIKVISION" in item1["designation"]
    assert item1["quantity"] == 14.0
    assert item1["unit"] == "U"
    assert item1["tva_rate"] == 20.0

    # Check Cable item
    item4 = items[3]
    assert "Câble" in item4["designation"]
    assert item4["quantity"] == 300.0
    assert item4["unit"] == "Ml"

def test_parse_results_fixture():
    fixture_path = FIXTURES_DIR / "results_page1.html"
    assert fixture_path.exists(), "Results fixture must exist"

    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    awards = parse_results_page(html)
    assert len(awards) == 10, "Results page 1 fixture must have 10 award cards"

    # Check awarded card
    awarded = [a for a in awards if a["status"] == "Attribué"]
    assert len(awarded) > 0, "Must have awarded items"
    first_awarded = awarded[0]
    assert first_awarded["winner_name"] != ""
    assert first_awarded["amount_ttc"] > 0
    assert first_awarded["devis_received_count"] is not None

