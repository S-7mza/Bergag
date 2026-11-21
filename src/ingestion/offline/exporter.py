import json
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from src.scraper.client import PortalHttpClient
from src.scraper.results_spider import ResultsSpider
from src.scraper.listing_spider import ListingSpider
from src.scraper.detail_spider import DetailSpider

logger = logging.getLogger(__name__)

OFFLINE_EXPORTS_DIR = Path("data/offline_exports")

class OfflineExporter:
    """
    Crawls procurement data (Awards or BDCs) locally without requiring
    an active database connection, bundling them into validated, portable
    offline export packages (.json) for later server upload.
    """
    def __init__(self, client: Optional[PortalHttpClient] = None):
        self.client = client

    def _compute_sha256(self, items: List[Dict[str, Any]]) -> str:
        serialized = json.dumps(items, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    async def collect_awards(
        self,
        max_pages: int = 5,
        page_size: int = 50,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Crawls historical awards and saves a portable bundle without connecting to DB.
        """
        start_time = datetime.now(timezone.utc)
        should_close = False
        client = self.client
        if client is None:
            client = PortalHttpClient()
            should_close = True

        spider = ResultsSpider(client)
        all_awards: List[Dict[str, Any]] = []
        portal_total_archive = 0

        logger.info(f"[OfflineExporter] Starting offline awards collection ({max_pages} pages, size={page_size})...")

        try:
            for page in range(1, max_pages + 1):
                logger.info(f"[OfflineExporter] Fetching awards page {page}/{max_pages}...")
                _, awards, total_count = await spider.fetch_results(
                    page=page,
                    page_size=page_size,
                    date_start=date_start,
                    date_end=date_end,
                    keyword=keyword,
                    category=category
                )
                portal_total_archive = total_count

                if not awards:
                    logger.info(f"[OfflineExporter] Page {page} returned 0 cards. End of archive.")
                    break

                for a in awards:
                    a["collected_at"] = datetime.now(timezone.utc).isoformat()
                    all_awards.append(a)

        finally:
            if should_close:
                await client.close()

        # Build bundle
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = Path(output_path) if output_path else (OFFLINE_EXPORTS_DIR / f"export_awards_{now_str}.json")
        out_file.parent.mkdir(parents=True, exist_ok=True)

        checksum = self._compute_sha256(all_awards)
        bundle = {
            "manifest": {
                "format_version": "1.0.0",
                "domain": "awards",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator": "Antigravity Offline Collector",
                "item_count": len(all_awards),
                "portal_total_archive": portal_total_archive,
                "sha256_checksum": checksum,
                "filters": {
                    "max_pages": max_pages,
                    "page_size": page_size,
                    "date_start": date_start,
                    "date_end": date_end,
                    "keyword": keyword,
                    "category": category
                }
            },
            "items": all_awards
        }

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2, ensure_ascii=False)

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(f"[OfflineExporter] Successfully exported {len(all_awards)} awards to {out_file} in {duration:.1f}s")

        return {
            "status": "success",
            "domain": "awards",
            "output_file": str(out_file),
            "item_count": len(all_awards),
            "portal_total_archive": portal_total_archive,
            "duration_seconds": round(duration, 1),
            "sha256_checksum": checksum
        }

    async def collect_bdc(
        self,
        max_pages: int = 2,
        page_size: int = 50,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Crawls active BDC notices with line items and saves a portable bundle without DB.
        """
        start_time = datetime.now(timezone.utc)
        should_close = False
        client = self.client
        if client is None:
            client = PortalHttpClient()
            should_close = True

        listing_spider = ListingSpider(client)
        detail_spider = DetailSpider(client)
        all_tenders: List[Dict[str, Any]] = []

        logger.info(f"[OfflineExporter] Starting offline BDC collection ({max_pages} pages)...")

        try:
            for page in range(1, max_pages + 1):
                _, cards = await listing_spider.fetch_page(page=page, page_size=page_size)
                if not cards:
                    break

                for card in cards:
                    portal_id = card.get("portal_id")
                    if not portal_id:
                        continue
                    try:
                        _, detail = await detail_spider.fetch_detail(portal_id)
                        detail["collected_at"] = datetime.now(timezone.utc).isoformat()
                        all_tenders.append(detail)
                    except Exception as e:
                        logger.warning(f"[OfflineExporter] Could not fetch detail for #{portal_id}: {e}")

        finally:
            if should_close:
                await client.close()

        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = Path(output_path) if output_path else (OFFLINE_EXPORTS_DIR / f"export_bdc_{now_str}.json")
        out_file.parent.mkdir(parents=True, exist_ok=True)

        checksum = self._compute_sha256(all_tenders)
        bundle = {
            "manifest": {
                "format_version": "1.0.0",
                "domain": "bdc",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator": "Antigravity Offline Collector",
                "item_count": len(all_tenders),
                "sha256_checksum": checksum
            },
            "items": all_tenders
        }

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2, ensure_ascii=False)

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(f"[OfflineExporter] Successfully exported {len(all_tenders)} BDCs to {out_file} in {duration:.1f}s")

        return {
            "status": "success",
            "domain": "bdc",
            "output_file": str(out_file),
            "item_count": len(all_tenders),
            "duration_seconds": round(duration, 1),
            "sha256_checksum": checksum
        }
