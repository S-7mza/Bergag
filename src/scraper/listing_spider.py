import hashlib
import logging
from typing import Tuple, Optional
from src.scraper.client import PortalHttpClient
from src.scraper.parser import parse_listing_page, parse_total_results
from src.models.raw import RawIngestionLog

logger = logging.getLogger(__name__)

class ListingSpider:
    """
    Crawls active BDC listings from /bdc/entreprise/consultation/
    using pageSize=50 for high efficiency and captures immutable raw snapshots.
    """
    def __init__(self, client: PortalHttpClient):
        self.client = client

    async def fetch_page(self, page: int = 1, page_size: int = 50) -> Tuple[RawIngestionLog, list[dict]]:
        url = f"/bdc/entreprise/consultation/?search_consultation_entreprise[pageSize]={page_size}&page={page}"
        logger.info(f"ListingSpider: Fetching page {page} with pageSize={page_size}")
        
        html = await self.client.get(url)
        content_hash = hashlib.sha256(html.encode('utf-8')).hexdigest()

        raw_log = RawIngestionLog(
            source_url=url,
            portal_id=None,
            page_type="listing",
            http_status=200,
            html_content=html,
            content_hash=content_hash,
            scraper_version="1.0.0"
        )

        cards = parse_listing_page(html)
        logger.info(f"ListingSpider: Parsed {len(cards)} tender cards from page {page}")
        
        return raw_log, cards

    async def fetch_active(self, page: int = 1, page_size: int = 50) -> Tuple[RawIngestionLog, list[dict], int]:
        """
        Fetches active consultations (submission deadline not arrived yet).
        Returns (raw_log, cards, total_active_count).
        """
        url = f"/bdc/entreprise/consultation/?search_consultation_entreprise[pageSize]={page_size}&page={page}"
        logger.info(f"ListingSpider: Fetching active listings page {page} with pageSize={page_size}")
        
        html = await self.client.get(url)
        content_hash = hashlib.sha256(html.encode('utf-8')).hexdigest()

        raw_log = RawIngestionLog(
            source_url=url,
            portal_id=None,
            page_type="listing_active",
            http_status=200,
            html_content=html,
            content_hash=content_hash,
            scraper_version="1.0.0"
        )

        cards = parse_listing_page(html)
        total_results = parse_total_results(html)
        if total_results == 0 and cards:
            total_results = len(cards)

        logger.info(f"ListingSpider: Found {total_results} active consultations on portal ({len(cards)} on page {page})")
        return raw_log, cards, total_results

    async def fetch_by_date(
        self, 
        date_str: str, 
        end_date_str: Optional[str] = None,
        page: int = 1, 
        page_size: int = 50
    ) -> Tuple[RawIngestionLog, list[dict], int]:
        """
        Fetches consultations filtered by official publication date or date range ('Date de mise en ligne').
        Returns (raw_log, cards, total_matching_results).
        """
        end_date = end_date_str or date_str
        url = (
            f"/bdc/entreprise/consultation/?"
            f"search_consultation_entreprise[dateMiseEnLigneStart]={date_str}&"
            f"search_consultation_entreprise[dateMiseEnLigneEnd]={end_date}&"
            f"search_consultation_entreprise[pageSize]={page_size}&page={page}"
        )
        logger.info(f"ListingSpider: Fetching for publication range {date_str} -> {end_date} (page {page}, size {page_size})")
        
        html = await self.client.get(url)
        content_hash = hashlib.sha256(html.encode('utf-8')).hexdigest()

        raw_log = RawIngestionLog(
            source_url=url,
            portal_id=None,
            page_type="listing_by_date",
            http_status=200,
            html_content=html,
            content_hash=content_hash,
            scraper_version="1.0.0"
        )

        cards = parse_listing_page(html)
        total_results = parse_total_results(html)
        if total_results == 0 and cards:
            total_results = len(cards)

        logger.info(f"ListingSpider: For date {date_str}, found {total_results} total results on portal ({len(cards)} cards on page {page})")
        return raw_log, cards, total_results

