import hashlib
import logging
from typing import Tuple
from src.scraper.client import PortalHttpClient
from src.scraper.parser import parse_results_page
from src.models.raw import RawIngestionLog

logger = logging.getLogger(__name__)

class ResultsSpider:
    """
    Crawls the historical BDC results & awards archive
    from /bdc/entreprise/consultation/resultat?page={page}
    capturing market prices, winners, and competition density.
    """
    def __init__(self, client: PortalHttpClient):
        self.client = client

    async def fetch_page(self, page: int = 1) -> Tuple[RawIngestionLog, list[dict]]:
        url = f"/bdc/entreprise/consultation/resultat?page={page}"
        logger.info(f"ResultsSpider: Fetching results page {page}")

        html = await self.client.get(url)
        content_hash = hashlib.sha256(html.encode('utf-8')).hexdigest()

        raw_log = RawIngestionLog(
            source_url=url,
            portal_id=None,
            page_type="result",
            http_status=200,
            html_content=html,
            content_hash=content_hash,
            scraper_version="1.0.0"
        )

        awards = parse_results_page(html)
        logger.info(f"ResultsSpider: Parsed {len(awards)} award cards from page {page}")

        return raw_log, awards

