import pytest
from src.scraper.client import PortalHttpClient

@pytest.mark.asyncio
async def test_live_portal_reachability():
    client = PortalHttpClient()
    try:
        # Fetch consultation page
        html = await client.get("/bdc/entreprise/consultation/?page=1")
        assert len(html) > 5000, "HTML should be non-empty"
        assert "Liste des avis d'achat" in html or "consultation" in html.lower()
    finally:
        await client.close()

