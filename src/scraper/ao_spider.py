import re
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from src.scraper.client import PortalHttpClient
from src.scraper.parser import clean_text, parse_date

logger = logging.getLogger(__name__)

class AoSpider:
    """
    Ingests formal Marchés Publics / Appels d'Offres (AO) from the main portal
    (index.php?page=entreprise.EntrepriseAdvancedSearch) into the same canonical
    database schema as BDC notices.
    """
    def __init__(self, client: PortalHttpClient):
        self.client = client
        self.search_url = "/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons"

    def parse_ao_listing(self, html: str) -> List[Dict[str, Any]]:
        """Parses formal tender listings from the main Atexo/Marco portal"""
        soup = BeautifulSoup(html, 'html.parser')
        tenders = []

        # Cards or table rows in main portal
        rows = soup.select('.table-results tbody tr, .search-results-item')
        if not rows:
            # Fallback for alternative Atexo DOM layouts
            rows = soup.select('tr[id*="ligne"]')

        for idx, row in enumerate(rows, start=1):
            ref_el = row.select_one('.reference, td:nth-child(2)')
            title_el = row.select_one('.objet, td:nth-child(3)')
            buyer_el = row.select_one('.organisme, td:nth-child(4)')
            deadline_el = row.select_one('.date-limite, td:nth-child(5)')
            link_el = row.select_one('a[href*="EntrepriseDetailConsultation"]')

            if not title_el:
                continue

            ref = clean_text(ref_el.get_text()) if ref_el else f"AO-{idx}"
            title = clean_text(title_el.get_text())
            buyer_name = clean_text(buyer_el.get_text()) if buyer_el else "Organisme Public"
            deadline_raw = clean_text(deadline_el.get_text()) if deadline_el else None

            # Extract internal consultation id
            portal_id = 900000 + idx
            if link_el:
                href = link_el.get('href', '')
                id_match = re.search(r'idLigne=(\d+)', href) or re.search(r'consultationId=(\d+)', href)
                if id_match:
                    portal_id = int(id_match.group(1))

            tenders.append({
                "portal_id": portal_id,
                "source_type": "marche_public",
                "reference": ref,
                "title": title,
                "buyer_name": buyer_name,
                "main_category": "Services" if "etude" in title.lower() else "Fournitures",
                "deadline_at": parse_date(deadline_raw),
                "status": "active"
            })

        return tenders

    async def fetch_recent_ao(self) -> List[Dict[str, Any]]:
        """Fetches active formal tenders from the main portal"""
        logger.info(f"AoSpider: Fetching main portal tenders from {self.search_url}")
        try:
            html = await self.client.get(self.search_url)
            tenders = self.parse_ao_listing(html)
            logger.info(f"AoSpider: Extracted {len(tenders)} formal tender notices")
            return tenders
        except Exception as e:
            logger.error(f"Error fetching main portal AO: {e}")
            return []

