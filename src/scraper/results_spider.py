import hashlib
import logging
from typing import Tuple, Optional
from src.scraper.client import PortalHttpClient
from src.scraper.parser import parse_results_page, parse_total_results
from src.models.raw import RawIngestionLog

logger = logging.getLogger(__name__)

class ResultsSpider:
    """
    Crawls the historical BDC results & awards archive
    from /bdc/entreprise/consultation/resultat
    capturing market prices, winners, and competition density.
    """
    def __init__(self, client: PortalHttpClient):
        self.client = client

    def _build_url(
        self,
        page: int = 1,
        page_size: int = 50,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        keyword: Optional[str] = None,
        category: Optional[str] = None
    ) -> str:
        params = [
            f"page={page}",
            f"search_consultation_resultats[pageSize]={page_size}"
        ]
        if date_start:
            params.append(f"search_consultation_resultats[dateMiseEnLigneStart]={date_start}")
        if date_end:
            params.append(f"search_consultation_resultats[dateMiseEnLigneEnd]={date_end}")
        if keyword:
            params.append(f"search_consultation_resultats[keyword]={keyword}")
        if category:
            params.append(f"search_consultation_resultats[categorie]={category}")

        return f"/bdc/entreprise/consultation/resultat?{'&'.join(params)}"

    async def fetch_page(
        self,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[RawIngestionLog, list[dict]]:
        """
        Backwards-compatible fetch returning (raw_log, awards).
        Uses pageSize=50 by default for 5x throughput.
        """
        raw_log, awards, _ = await self.fetch_results(page=page, page_size=page_size)
        return raw_log, awards

    async def fetch_results(
        self,
        page: int = 1,
        page_size: int = 50,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        keyword: Optional[str] = None,
        category: Optional[str] = None
    ) -> Tuple[RawIngestionLog, list[dict], int]:
        """
        Fetches a page of award cards with optional date and category filters.
        Returns (raw_log, awards, total_available_on_portal).
        """
        url = self._build_url(
            page=page,
            page_size=page_size,
            date_start=date_start,
            date_end=date_end,
            keyword=keyword,
            category=category
        )
        logger.info(f"ResultsSpider: Fetching results page {page} (size={page_size}) from {url}")

        html = await self.client.get(url)
        content_hash = hashlib.sha256(html.encode('utf-8')).hexdigest()

        raw_log = RawIngestionLog(
            source_url=url,
            portal_id=None,
            page_type="result",
            http_status=200,
            html_content=html,
            content_hash=content_hash,
            scraper_version="1.1.0"
        )

        awards = parse_results_page(html)
        total_count = parse_total_results(html)
        logger.info(f"ResultsSpider: Parsed {len(awards)} award cards (portal reports {total_count} total)")

        return raw_log, awards, total_count
