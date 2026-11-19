import hashlib
import logging
from typing import Tuple
from src.scraper.client import PortalHttpClient
from src.scraper.parser import parse_detail_page
from src.models.raw import RawIngestionLog

logger = logging.getLogger(__name__)

class DetailSpider:
    """
    Fetches full consultation details and structured accordion line items
    from /bdc/entreprise/consultation/show/{portal_id}.
    """
    def __init__(self, client: PortalHttpClient):
        self.client = client

    async def fetch_detail(self, portal_id: int) -> Tuple[RawIngestionLog, dict]:
        url = f"/bdc/entreprise/consultation/show/{portal_id}"
        logger.info(f"DetailSpider: Fetching tender #{portal_id}")

        html = await self.client.get(url)
        content_hash = hashlib.sha256(html.encode('utf-8')).hexdigest()

        raw_log = RawIngestionLog(
            source_url=url,
            portal_id=portal_id,
            page_type="detail",
            http_status=200,
            html_content=html,
            content_hash=content_hash,
            scraper_version="1.0.0"
        )

        detail_data = parse_detail_page(html, portal_id=portal_id)
        logger.info(f"DetailSpider: Extracted {len(detail_data['line_items'])} line items for tender #{portal_id}")

        return raw_log, detail_data

