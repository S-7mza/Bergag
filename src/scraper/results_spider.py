import re
import hashlib
import logging
from typing import Tuple, Optional
from datetime import datetime
from src.scraper.client import PortalHttpClient
from src.scraper.parser import parse_results_page, parse_total_results
from src.models.raw import RawIngestionLog

logger = logging.getLogger(__name__)

def _sanitize_param(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    val = val.strip()
    if val.lower() in (
        "aucun", "none", "null", "all", "tout", "",
        "tous les secteurs", "tous les marches", "tous les marchés",
        "tous", "tous secteurs", "toutes", "tous marchÃ©s"
    ):
        return None
    return val

def _sanitize_date(val: Optional[str]) -> Optional[str]:
    val = _sanitize_param(val)
    if not val:
        return None
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", val):
        return val
    logger.warning(f"ResultsSpider: Date invalide ignorée '{val}' (attendu: JJ/MM/AAAA)")
    return None

class ResultsSpider:
    """
    Crawls the historical BDC results & awards archive
    from /bdc/entreprise/consultation/resultat
    capturing market prices, winners, and competition density.

    NOTE ON WAF RESILIENCE:
    The DGSSI / F5 BIG-IP ASM WAF on marchespublics.gov.ma returns HTTP 403 Forbidden
    if 'dateMiseEnLigneStart', 'dateMiseEnLigneEnd', 'keyword', or 'categorie' parameters
    are appended to GET query strings.
    Only 'page' and 'search_consultation_resultats[pageSize]' are permitted by the WAF.
    All date and keyword filtering is applied safely and reliably client-side in Python.
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
        # Strictly return clean URL allowed by F5 WAF
        return f"/bdc/entreprise/consultation/resultat?page={page}&search_consultation_resultats%5BpageSize%5D={page_size}"

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
        Fetches a page of award cards with optional date, keyword, and category filters.
        Filtering is applied client-side to prevent triggering F5 WAF 403 errors.
        Returns (raw_log, awards, total_available_on_portal).
        """
        url = self._build_url(page=page, page_size=page_size)
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
            scraper_version="1.2.0"
        )

        awards = parse_results_page(html)
        total_count = parse_total_results(html)

        # Client-side keyword filtering to avoid F5 WAF 403
        clean_kw = _sanitize_param(keyword)
        if clean_kw:
            kw_low = clean_kw.lower()
            awards = [
                a for a in awards
                if kw_low in (a.get("title") or "").lower()
                or kw_low in (a.get("reference") or "").lower()
                or kw_low in (a.get("buyer_name") or "").lower()
                or kw_low in (a.get("winner_name") or a.get("winning_bidder") or "").lower()
            ]

        # Client-side date filtering to avoid F5 WAF 403
        s_date = _sanitize_date(date_start)
        e_date = _sanitize_date(date_end)
        if s_date or e_date:
            dt_start = None
            dt_end = None
            if s_date:
                try:
                    p = [int(x) for x in s_date.split("/")]
                    dt_start = datetime(p[2], p[1], p[0], 0, 0, 0)
                except Exception:
                    pass
            if e_date:
                try:
                    p = [int(x) for x in e_date.split("/")]
                    dt_end = datetime(p[2], p[1], p[0], 23, 59, 59)
                except Exception:
                    pass

            filtered = []
            for a in awards:
                pub = a.get("published_at")
                if pub:
                    try:
                        pub_dt = datetime.fromisoformat(pub).replace(tzinfo=None)
                        if dt_start and pub_dt < dt_start:
                            continue
                        if dt_end and pub_dt > dt_end:
                            continue
                    except Exception:
                        pass
                filtered.append(a)
            awards = filtered

        logger.info(f"ResultsSpider: Parsed {len(awards)} award cards (portal reports {total_count} total)")
        return raw_log, awards, total_count
