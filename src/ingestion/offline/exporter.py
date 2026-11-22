import os
import json
import math
import asyncio
import calendar
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Set, Callable, Tuple

from src.scraper.client import PortalHttpClient
from src.scraper.results_spider import ResultsSpider
from src.scraper.listing_spider import ListingSpider
from src.scraper.detail_spider import DetailSpider

logger = logging.getLogger(__name__)

OFFLINE_EXPORTS_DIR = Path("data/offline_exports")
CHECKPOINT_BDC = OFFLINE_EXPORTS_DIR / ".bdc_checkpoint.json"
CHECKPOINT_AWARDS = OFFLINE_EXPORTS_DIR / ".awards_checkpoint.json"


class OfflineExporter:
    """
    Crawls procurement data (Awards or BDCs) locally without requiring
    an active database connection, bundling them into validated, portable
    offline export packages (.json) for later server upload.

    Features:
    - Resumable crawling with checkpoints (.bdc_checkpoint.json)
    - Incremental atomic disk flushes after every page (zero data loss on crash/exit)
    - Full active archive collection ("all" pages)
    - Direction control ("asc": oldest to newest, "desc": newest to oldest)
    - Live progress callbacks & telemetry
    """

    def __init__(self, client: Optional[PortalHttpClient] = None):
        self.client = client
        OFFLINE_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def _compute_sha256(self, items: List[Dict[str, Any]]) -> str:
        serialized = json.dumps(items, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def get_checkpoint(domain: str = "bdc") -> Optional[Dict[str, Any]]:
        cp_file = CHECKPOINT_BDC if domain == "bdc" else CHECKPOINT_AWARDS
        if cp_file.exists():
            try:
                with open(cp_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    @staticmethod
    def clear_checkpoint(domain: str = "bdc"):
        cp_file = CHECKPOINT_BDC if domain == "bdc" else CHECKPOINT_AWARDS
        if cp_file.exists():
            try:
                cp_file.unlink()
            except Exception:
                pass

    @staticmethod
    def _atomic_write_json(file_path: Path, data: Dict[str, Any]):
        tmp_file = file_path.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp_file.replace(file_path)

    async def collect_awards(
        self,
        max_pages: Optional[int] = 5,
        page_size: int = 50,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        output_path: Optional[str] = None,
        resume: bool = True,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Crawls historical awards and saves a portable bundle without connecting to DB.
        Supports resume via checkpoint and incremental disk flushing.
        
        Parameters:
        - max_pages: Number of pages to collect. If None or <= 0, collects ALL available pages.
        - page_size: Items per request (default: 50).
        - date_start: Start date filter (DD/MM/YYYY).
        - date_end: End date filter (DD/MM/YYYY).
        - keyword: Optional search keyword.
        - category: Optional category ID.
        - output_path: Explicit target JSON file path.
        - resume: If True, resumes unfinished checkpoint.
        """
        start_time = datetime.now(timezone.utc)
        should_close = False
        client = self.client
        if client is None:
            client = PortalHttpClient()
            should_close = True

        spider = ResultsSpider(client)
        all_awards: List[Dict[str, Any]] = []
        collected_refs: Set[str] = set()
        portal_total_archive = 0
        completed_pages: List[int] = []
        target_pages: List[int] = []

        cp = self.get_checkpoint("awards") if resume else None
        if cp and cp.get("status") == "in_progress":
            out_file = Path(cp["output_file"])
            if out_file.exists():
                try:
                    with open(out_file, "r", encoding="utf-8") as f:
                        bundle_data = json.load(f)
                        all_awards = bundle_data.get("items", [])
                        collected_refs = {a.get("reference") for a in all_awards if a.get("reference")}
                        completed_pages = cp.get("completed_pages", [])
                        target_pages = cp.get("target_pages", [])
                        portal_total_archive = cp.get("portal_total", 0)
                        logger.info(f"[OfflineExporter] Resuming awards crawl: {len(all_awards)} items already loaded.")
                except Exception as e:
                    logger.warning(f"Failed to load checkpoint file: {e}")
        else:
            now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_file = Path(output_path) if output_path else (OFFLINE_EXPORTS_DIR / f"export_awards_{now_str}.json")

        out_file.parent.mkdir(parents=True, exist_ok=True)

        # Parse date filters if provided
        dt_filter_start = None
        dt_filter_end = None
        if date_start:
            try:
                p = [int(x) for x in date_start.split("/")]
                dt_filter_start = datetime(p[2], p[1], p[0], 0, 0, 0)
            except Exception:
                pass
        if date_end:
            try:
                p = [int(x) for x in date_end.split("/")]
                dt_filter_end = datetime(p[2], p[1], p[0], 23, 59, 59)
            except Exception:
                pass

        # Probe portal to determine total pages and fetch page 1 if needed
        if not target_pages:
            logger.info(f"[OfflineExporter] Probing portal for awards count (date: {date_start or '*'} to {date_end or '*'})...")
            _, probe_raw_awards, total_count = await spider.fetch_results(
                page=1,
                page_size=page_size,
                keyword=keyword,
                category=category
            )
            portal_total_archive = total_count
            total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1

            if max_pages is None or max_pages <= 0 or max_pages >= total_pages:
                target_pages = list(range(1, total_pages + 1))
            else:
                target_pages = list(range(1, max_pages + 1))

            if 1 not in completed_pages and probe_raw_awards:
                for a in probe_raw_awards:
                    pub_str = a.get("published_at")
                    if pub_str and (dt_filter_start or dt_filter_end):
                        try:
                            pub_dt = datetime.fromisoformat(pub_str).replace(tzinfo=None)
                            if dt_filter_start and pub_dt < dt_filter_start:
                                continue
                            if dt_filter_end and pub_dt > dt_filter_end:
                                continue
                        except Exception:
                            pass
                    ref = a.get("reference")
                    if ref and ref in collected_refs:
                        continue
                    a["collected_at"] = datetime.now(timezone.utc).isoformat()
                    all_awards.append(a)
                    if ref:
                        collected_refs.add(ref)
                completed_pages.append(1)

                checksum = self._compute_sha256(all_awards)
                bundle = {
                    "manifest": {
                        "format_version": "1.0.0",
                        "domain": "awards",
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "generator": "Antigravity Offline Resumable Collector",
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
                self._atomic_write_json(out_file, bundle)

                if progress_callback:
                    progress_callback({
                        "domain": "awards",
                        "page": 1,
                        "total_pages": len(target_pages),
                        "items_collected": len(all_awards),
                        "portal_total": portal_total_archive
                    })

        pages_to_run = [p for p in target_pages if p not in completed_pages]
        logger.info(f"[OfflineExporter] Starting awards collection ({len(pages_to_run)} pages remaining of {len(target_pages)})...")

        try:
            for page in pages_to_run:
                logger.info(f"[OfflineExporter] Fetching awards page {page}/{target_pages[-1]}...")
                _, raw_awards, total_count = await spider.fetch_results(
                    page=page,
                    page_size=page_size,
                    keyword=keyword,
                    category=category
                )
                portal_total_archive = total_count

                if not raw_awards:
                    logger.info(f"[OfflineExporter] Page {page} returned 0 cards. End of archive.")
                    break

                all_older_than_start = bool(dt_filter_start)
                page_kept = []

                for a in raw_awards:
                    pub_str = a.get("published_at")
                    if pub_str:
                        try:
                            pub_dt = datetime.fromisoformat(pub_str).replace(tzinfo=None)
                            if dt_filter_start and pub_dt >= dt_filter_start:
                                all_older_than_start = False
                            if dt_filter_start and pub_dt < dt_filter_start:
                                continue
                            if dt_filter_end and pub_dt > dt_filter_end:
                                continue
                        except Exception:
                            all_older_than_start = False
                    else:
                        all_older_than_start = False
                    page_kept.append(a)

                for a in page_kept:
                    ref = a.get("reference")
                    if ref and ref in collected_refs:
                        continue
                    a["collected_at"] = datetime.now(timezone.utc).isoformat()
                    all_awards.append(a)
                    if ref:
                        collected_refs.add(ref)

                completed_pages.append(page)

                # Incremental flush to disk
                checksum = self._compute_sha256(all_awards)
                bundle = {
                    "manifest": {
                        "format_version": "1.0.0",
                        "domain": "awards",
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "generator": "Antigravity Offline Resumable Collector",
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
                self._atomic_write_json(out_file, bundle)

                # Update checkpoint
                self._atomic_write_json(CHECKPOINT_AWARDS, {
                    "domain": "awards",
                    "output_file": str(out_file),
                    "completed_pages": completed_pages,
                    "target_pages": target_pages,
                    "last_completed_page": page,
                    "item_count": len(all_awards),
                    "portal_total": portal_total_archive,
                    "status": "in_progress"
                })

                if progress_callback:
                    progress_callback({
                        "domain": "awards",
                        "page": page,
                        "total_pages": len(target_pages),
                        "items_collected": len(all_awards),
                        "portal_total": portal_total_archive
                    })

                if dt_filter_start and all_older_than_start:
                    logger.info(f"[OfflineExporter] Page {page} cards are all older than date_start {date_start}. Stopping early.")
                    break

            # Completed all pages
            self.clear_checkpoint("awards")

        finally:
            if should_close:
                await client.close()

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        checksum = self._compute_sha256(all_awards)
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

    async def _collect_awards_streaming_buckets(
        self,
        target_months: List[Tuple[int, int]],
        max_pages_per_month: Optional[int] = None,
        page_size: int = 50,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        output_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Core streaming engine for monthly awards extraction.
        Walks portal results page by page in natural reverse-chronological order
        and distributes award cards directly into monthly JSON bundles on disk.
        Stops early once the crawler reaches past the earliest target date.
        """
        out_dir = output_dir or OFFLINE_EXPORTS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        target_set = set(target_months)
        if not target_set:
            return []

        sorted_targets = sorted(target_months)
        min_y, min_m = sorted_targets[0]
        earliest_target_date = datetime(min_y, min_m, 1, 0, 0, 0)

        month_buckets: Dict[Tuple[int, int], List[Dict[str, Any]]] = {
            t: [] for t in target_months
        }
        collected_refs: Set[str] = set()
        max_items_per_month = (max_pages_per_month * page_size) if (max_pages_per_month and max_pages_per_month > 0) else None

        should_close = False
        client = self.client
        if client is None:
            client = PortalHttpClient()
            should_close = True

        spider = ResultsSpider(client)
        start_time = datetime.now(timezone.utc)
        portal_total_archive = 0

        logger.info(
            f"[OfflineExporter] Starting streaming collection for {len(target_months)} months "
            f"(Earliest date threshold: {earliest_target_date.strftime('%d/%m/%Y')})..."
        )

        try:
            page = 1
            consecutive_empty = 0
            month_pages_seen: Dict[Tuple[int, int], Set[int]] = {t: set() for t in target_months}

            while True:
                _, raw_awards, total_count = await spider.fetch_results(
                    page=page,
                    page_size=page_size,
                    keyword=keyword,
                    category=category
                )
                portal_total_archive = total_count
                total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1

                if not raw_awards:
                    consecutive_empty += 1
                    if consecutive_empty >= 2 or page > 1:
                        logger.info(f"[OfflineExporter] Page {page} returned 0 cards. End of archive reached.")
                        break
                    page += 1
                    continue

                consecutive_empty = 0
                all_older_than_earliest = True
                new_cards_added = 0

                for a in raw_awards:
                    ref = a.get("reference")
                    pub_str = a.get("published_at")
                    if not pub_str:
                        all_older_than_earliest = False
                        continue

                    try:
                        pub_dt = datetime.fromisoformat(pub_str).replace(tzinfo=None)
                    except Exception:
                        pub_dt = None

                    if pub_dt:
                        if pub_dt >= earliest_target_date:
                            all_older_than_earliest = False

                        bucket_key = (pub_dt.year, pub_dt.month)
                        if bucket_key in target_set:
                            month_pages_seen[bucket_key].add(page)
                            if max_items_per_month and len(month_buckets[bucket_key]) >= max_items_per_month:
                                continue
                            if max_pages_per_month and len(month_pages_seen[bucket_key]) > max_pages_per_month:
                                continue
                            if ref and ref in collected_refs:
                                continue
                            a["collected_at"] = datetime.now(timezone.utc).isoformat()
                            month_buckets[bucket_key].append(a)
                            new_cards_added += 1
                            if ref:
                                collected_refs.add(ref)
                    else:
                        all_older_than_earliest = False

                # Incremental flush for all target months that have items
                for (y, m), items in month_buckets.items():
                    if items:
                        m_file = out_dir / f"export_awards_{y}_{m:02d}.json"
                        csum = self._compute_sha256(items)
                        b_data = {
                            "manifest": {
                                "format_version": "1.0.0",
                                "domain": "awards",
                                "year": y,
                                "month": m,
                                "generated_at": datetime.now(timezone.utc).isoformat(),
                                "generator": "Antigravity Offline Resumable Collector",
                                "item_count": len(items),
                                "portal_total_archive": portal_total_archive,
                                "sha256_checksum": csum,
                                "filters": {
                                    "year": y,
                                    "month": m,
                                    "keyword": keyword,
                                    "max_pages_per_month": max_pages_per_month
                                }
                            },
                            "items": items
                        }
                        self._atomic_write_json(m_file, b_data)

                total_collected = sum(len(items) for items in month_buckets.values())
                if progress_callback:
                    progress_callback({
                        "domain": "awards",
                        "page": page,
                        "total_pages": total_pages,
                        "items_collected": total_collected,
                        "portal_total": portal_total_archive
                    })

                # Stop conditions:
                # 1. Total portal pages reached
                if page >= total_pages:
                    logger.info(f"[OfflineExporter] Page {page} reached total portal pages ({total_pages}). Stopping.")
                    break

                # 2. No new cards on this page (duplicate cycle / mock loop)
                if new_cards_added == 0 and len(raw_awards) > 0:
                    logger.info(f"[OfflineExporter] Page {page} contained no new cards. Stopping.")
                    break

                # 3. All cards on page are older than earliest target date
                if all_older_than_earliest:
                    logger.info(
                        f"[OfflineExporter] Page {page} dates are all older than {earliest_target_date.strftime('%d/%m/%Y')}. "
                        f"Target period completed. Stopping crawl early."
                    )
                    break

                # 4. Quota reached for all target months
                if max_items_per_month and all(len(month_buckets[k]) >= max_items_per_month for k in target_set):
                    logger.info("[OfflineExporter] Tous les mois ciblés ont atteint leur quota maximum d'éléments.")
                    break

                page += 1
                await asyncio.sleep(0.05)

        finally:
            if should_close:
                await client.close()

        # Final pass: write all target month files and return summary
        results = []
        for (y, m) in target_months:
            items = month_buckets.get((y, m), [])
            m_file = out_dir / f"export_awards_{y}_{m:02d}.json"
            csum = self._compute_sha256(items)
            b_data = {
                "manifest": {
                    "format_version": "1.0.0",
                    "domain": "awards",
                    "year": y,
                    "month": m,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "generator": "Antigravity Offline Resumable Collector",
                    "item_count": len(items),
                    "portal_total_archive": portal_total_archive,
                    "sha256_checksum": csum,
                    "filters": {
                        "year": y,
                        "month": m,
                        "keyword": keyword,
                        "max_pages_per_month": max_pages_per_month
                    }
                },
                "items": items
            }
            self._atomic_write_json(m_file, b_data)
            results.append({
                "status": "success",
                "domain": "awards",
                "output_file": str(m_file),
                "month": m,
                "year": y,
                "item_count": len(items),
                "portal_total_archive": portal_total_archive,
                "sha256_checksum": csum
            })

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        total_items = sum(r["item_count"] for r in results)
        logger.info(
            f"[OfflineExporter] Monthly awards collection finished: "
            f"{total_items} awards across {len(results)} monthly files in {duration:.1f}s"
        )
        return results

    async def collect_awards_by_months(
        self,
        year: int,
        start_month: int = 1,
        end_month: int = 12,
        max_pages_per_month: Optional[int] = None,
        page_size: int = 50,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        output_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Collects awards archive in structured monthly bulks in a single streaming chronological pass.
        Each month is saved into its own portable offline bundle file with manifest:
          data/offline_exports/export_awards_{year}_{m:02d}.json
        """
        start_month = max(1, min(12, start_month))
        end_month = max(1, min(12, end_month))
        if start_month > end_month:
            start_month, end_month = end_month, start_month

        target_months = [(year, m) for m in range(start_month, end_month + 1)]
        return await self._collect_awards_streaming_buckets(
            target_months=target_months,
            max_pages_per_month=max_pages_per_month,
            page_size=page_size,
            keyword=keyword,
            category=category,
            output_dir=output_dir,
            progress_callback=progress_callback
        )

    async def collect_awards_recent_months(
        self,
        n_months: int = 6,
        max_pages_per_month: Optional[int] = None,
        page_size: int = 50,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        output_dir: Optional[Path] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Collects awards for the last N rolling months (e.g. last 3, 6, 12 months) month by month
        in a single streaming chronological pass.
        """
        now = datetime.now()
        month_tuples = []
        y, m = now.year, now.month
        for _ in range(n_months):
            month_tuples.append((y, m))
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        month_tuples.reverse()

        return await self._collect_awards_streaming_buckets(
            target_months=month_tuples,
            max_pages_per_month=max_pages_per_month,
            page_size=page_size,
            keyword=keyword,
            category=category,
            output_dir=output_dir,
            progress_callback=progress_callback
        )

    async def collect_bdc(
        self,
        max_pages: Optional[int] = None,
        page_size: int = 50,
        order: str = "desc",
        resume: bool = True,
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Crawls active BDC notices with line items and saves a portable bundle without DB.

        Parameters:
        - max_pages: Number of pages to collect. If None or <= 0, collects ALL active pages on portal.
        - page_size: Items per request (default 50).
        - order: 'asc' (oldest to newest) or 'desc' (newest to oldest).
        - resume: If True and an unfinished checkpoint exists, resumes from the last completed page.
        - output_path: Optional explicit target JSON file path.
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
        collected_ids: Set[int] = set()
        completed_pages: List[int] = []

        # 1. Probe portal for total active count & total pages
        logger.info("[OfflineExporter] Probing portal for active BDC count...")
        _, _, total_active_count = await listing_spider.fetch_active(page=1, page_size=page_size)
        total_pages = max(1, math.ceil(total_active_count / page_size))
        logger.info(f"[OfflineExporter] Portal reports {total_active_count} active notices (~{total_pages} pages).")

        # 2. Determine target pages
        if max_pages is None or max_pages <= 0 or max_pages >= total_pages:
            num_pages = total_pages
        else:
            num_pages = max_pages

        if order == "asc":
            # Oldest to newest: start from last page (total_pages) down to total_pages - num_pages + 1
            target_pages = list(range(total_pages, total_pages - num_pages, -1))
        else:
            # Newest to oldest: start from page 1 up to num_pages
            target_pages = list(range(1, num_pages + 1))

        # 3. Check for existing checkpoint
        cp = self.get_checkpoint("bdc") if resume else None
        if cp and cp.get("status") == "in_progress":
            out_file = Path(cp["output_file"])
            if out_file.exists():
                try:
                    with open(out_file, "r", encoding="utf-8") as f:
                        bundle_data = json.load(f)
                        all_tenders = bundle_data.get("items", [])
                        collected_ids = {t.get("portal_id") for t in all_tenders if t.get("portal_id")}
                        completed_pages = cp.get("completed_pages", [])
                        order = cp.get("order", order)
                        target_pages = cp.get("target_pages", target_pages)
                        logger.info(f"[OfflineExporter] Resuming BDC crawl: {len(all_tenders)} notices already loaded.")
                except Exception as e:
                    logger.warning(f"Could not load existing BDC bundle for resume: {e}")
        else:
            now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            order_label = "old_to_new" if order == "asc" else "new_to_old"
            all_label = "all_" if (max_pages is None or max_pages <= 0) else f"{num_pages}p_"
            out_file = Path(output_path) if output_path else (OFFLINE_EXPORTS_DIR / f"export_bdc_{all_label}{order_label}_{now_str}.json")

        out_file.parent.mkdir(parents=True, exist_ok=True)
        pages_to_run = [p for p in target_pages if p not in completed_pages]

        logger.info(
            f"[OfflineExporter] Starting BDC collection: {len(pages_to_run)} pages remaining "
            f"(order={order}, total={len(target_pages)} pages)..."
        )

        try:
            for page_idx, page in enumerate(pages_to_run, 1):
                logger.info(f"[OfflineExporter] Fetching BDC listing page {page} ({page_idx}/{len(pages_to_run)})...")
                _, cards = await listing_spider.fetch_page(page=page, page_size=page_size)
                if not cards:
                    logger.info(f"[OfflineExporter] Page {page} returned 0 cards.")
                    completed_pages.append(page)
                    continue

                # If oldest to newest, reverse cards on the page so the oldest notice is first
                if order == "asc":
                    cards = list(reversed(cards))

                for card_idx, card in enumerate(cards, 1):
                    portal_id = card.get("portal_id")
                    if not portal_id or portal_id in collected_ids:
                        continue
                    try:
                        _, detail = await detail_spider.fetch_detail(portal_id)
                        detail["collected_at"] = datetime.now(timezone.utc).isoformat()
                        all_tenders.append(detail)
                        collected_ids.add(portal_id)

                        if progress_callback:
                            progress_callback({
                                "domain": "bdc",
                                "current_page": page,
                                "total_pages": len(target_pages),
                                "completed_pages_count": len(completed_pages),
                                "card_index": card_idx,
                                "cards_on_page": len(cards),
                                "items_collected": len(all_tenders),
                                "total_active_portal": total_active_count,
                                "current_item": detail
                            })
                    except Exception as e:
                        logger.warning(f"[OfflineExporter] Could not fetch detail for #{portal_id}: {e}")

                completed_pages.append(page)

                # Incremental atomic flush to disk after every page
                checksum = self._compute_sha256(all_tenders)
                bundle = {
                    "manifest": {
                        "format_version": "1.0.0",
                        "domain": "bdc",
                        "order": order,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "generator": "Antigravity Offline Resumable Collector",
                        "item_count": len(all_tenders),
                        "total_active_archive": total_active_count,
                        "completed_pages": completed_pages,
                        "target_pages": target_pages,
                        "is_complete": len(completed_pages) == len(target_pages),
                        "sha256_checksum": checksum
                    },
                    "items": all_tenders
                }
                self._atomic_write_json(out_file, bundle)

                # Update checkpoint
                self._atomic_write_json(CHECKPOINT_BDC, {
                    "domain": "bdc",
                    "order": order,
                    "output_file": str(out_file),
                    "total_active_count": total_active_count,
                    "total_pages": total_pages,
                    "target_pages": target_pages,
                    "completed_pages": completed_pages,
                    "last_completed_page": page,
                    "items_count": len(all_tenders),
                    "collected_ids": list(collected_ids),
                    "last_updated_at": datetime.now(timezone.utc).isoformat(),
                    "status": "in_progress"
                })

            # Finished all target pages
            self.clear_checkpoint("bdc")

        finally:
            if should_close:
                await client.close()

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        checksum = self._compute_sha256(all_tenders)
        logger.info(f"[OfflineExporter] Successfully exported {len(all_tenders)} BDCs to {out_file} in {duration:.1f}s")

        return {
            "status": "success",
            "domain": "bdc",
            "order": order,
            "output_file": str(out_file),
            "item_count": len(all_tenders),
            "total_active_archive": total_active_count,
            "duration_seconds": round(duration, 1),
            "sha256_checksum": checksum
        }
