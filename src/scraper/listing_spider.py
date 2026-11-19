import hashlib
import logging
from typing import Tuple
from src.scraper.client import PortalHttpClient
from src.scraper.parser import parse_listing_page
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

