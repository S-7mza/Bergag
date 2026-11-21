import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from src.database.session import async_session_factory
from src.scraper.client import PortalHttpClient
from src.scraper.results_spider import ResultsSpider
from src.ingestion.awards.service import AwardsIngestionService
from src.ingestion.base import ProgressCallback, AbortCheckCallback

logger = logging.getLogger(__name__)

AWARDS_LEDGER_FILE = Path("data/awards_batches_ledger.json")

class AwardsIngestionPipeline:
    """
    Dedicated high-throughput pipeline orchestrating Moroccan Public Procurement
    awards synchronization (/bdc/entreprise/consultation/resultat).
    """
    def __init__(self, client: Optional[PortalHttpClient] = None):
        self.client = client

    def _persist_to_ledger(self, record: Dict[str, Any]):
        try:
            AWARDS_LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
            existing: List[Dict[str, Any]] = []
            if AWARDS_LEDGER_FILE.exists():
                try:
                    with open(AWARDS_LEDGER_FILE, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    existing = []
            
            existing.insert(0, record)
            # Keep last 100 runs
            existing = existing[:100]
            with open(AWARDS_LEDGER_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not persist to awards ledger: {e}")

    async def run(
        self,
        max_pages: int = 5,
        page_size: int = 50,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        is_aborted_callback: Optional[AbortCheckCallback] = None,
        batch_id: Optional[str] = None,
        triggered_by: str = "Opérateur (Manuel)"
    ) -> Dict[str, Any]:
        """
        Executes an autonomous awards synchronization cycle:
        1. Emits execution plan event.
        2. Crawls results archive pages at pageSize=50.
        3. Parses awards, winners, amounts TTC, and devis counts.
        4. Ingests into 'awards' table with per-card transaction safety.
        5. Cross-links matching Tenders and updates their status.
        6. Logs execution to dual-persistence JSON ledger.
        """
        start_time = datetime.now(timezone.utc)
        batch_id = batch_id or f"AW-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"

        logger.info(f"[{batch_id}] Starting Awards Ingestion Pipeline (max_pages={max_pages}, size={page_size})...")

        if progress_callback:
            try:
                await progress_callback("plan_initialized", {
                    "domain": "awards",
                    "batch_id": batch_id,
                    "phase": "plan",
                    "max_pages": max_pages,
                    "page_size": page_size,
                    "estimated_awards": max_pages * page_size,
                    "target_url": "https://www.marchespublics.gov.ma/bdc/entreprise/consultation/resultat",
                    "step_description": f"Phase 1 : Plan validé. Scan de {max_pages} pages (~{max_pages * page_size} attributions TGR)"
                })
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

        should_close_client = False
        client = self.client
        if client is None:
            client = PortalHttpClient()
            should_close_client = True

        spider = ResultsSpider(client)
        total_ingested = 0
        total_errors = 0
        pages_completed = 0
        portal_total_archive = 0
        recent_awards: List[Dict[str, Any]] = []

        try:
            async with async_session_factory() as session:
                service = AwardsIngestionService(session, client)

                for page in range(1, max_pages + 1):
                    if is_aborted_callback and is_aborted_callback():
                        logger.info(f"[{batch_id}] Awards crawl cycle aborted by operator at page loop.")
                        break

                    if progress_callback:
                        try:
                            await progress_callback("page_discovery", {
                                "domain": "awards",
                                "batch_id": batch_id,
                                "phase": "discovery",
                                "page": page,
                                "max_pages": max_pages,
                                "step_description": f"Phase 2 : Scan de la page de résultats {page}/{max_pages}..."
                            })
                        except Exception:
                            pass

                    try:
                        raw_log, awards, portal_total = await spider.fetch_results(
                            page=page,
                            page_size=page_size,
                            date_start=date_start,
                            date_end=date_end,
                            keyword=keyword,
                            category=category
                        )
                        portal_total_archive = portal_total
                        session.add(raw_log)
                        await session.commit()

                        if not awards:
                            logger.info(f"[{batch_id}] Results page {page} returned 0 awards. Reached archive end.")
                            break

                        pages_completed += 1

                        if progress_callback:
                            try:
                                await progress_callback("awards_found", {
                                    "domain": "awards",
                                    "batch_id": batch_id,
                                    "phase": "discovery",
                                    "page": page,
                                    "awards_count": len(awards),
                                    "portal_total": portal_total,
                                    "step_description": f"Phase 2 : {len(awards)} attributions extraites sur la page {page}."
                                })
                            except Exception:
                                pass

                        for a in awards:
                            if is_aborted_callback and is_aborted_callback():
                                break

                            try:
                                # Isolated subtransaction per award
                                award_obj = await service.ingest_award(a)
                                await session.commit()
                                total_ingested += 1

                                award_summary = {
                                    "reference": award_obj.reference,
                                    "winner_name": award_obj.winner_name,
                                    "amount_ttc": float(award_obj.amount_ttc),
                                    "status": award_obj.status,
                                    "buyer": award_obj.buyer_name_raw[:45],
                                    "tender_linked": bool(award_obj.tender_id)
                                }
                                recent_awards.append(award_summary)

                                if progress_callback:
                                    try:
                                        await progress_callback("award_ingested", {
                                            "domain": "awards",
                                            "batch_id": batch_id,
                                            "phase": "award_item",
                                            "processed_count": total_ingested,
                                            "estimated_total": max_pages * page_size,
                                            "award": award_summary,
                                            "step_description": f"Phase 3 : Ingestion attribution « {award_obj.reference} » → {award_obj.winner_name} ({float(award_obj.amount_ttc):,.0f} MAD)"
                                        })
                                    except Exception:
                                        pass

                            except Exception as item_err:
                                total_errors += 1
                                logger.error(f"Failed to ingest award card {a.get('reference')}: {item_err}")
                                await session.rollback()

                    except Exception as page_err:
                        logger.error(f"Failed to crawl results page {page}: {page_err}")
                        total_errors += 1
                        break

        finally:
            if should_close_client:
                await client.close()

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        status = "aborted" if (is_aborted_callback and is_aborted_callback()) else ("completed" if total_errors == 0 else "completed_with_errors")

        summary = {
            "batch_id": batch_id,
            "status": status,
            "domain": "awards",
            "triggered_by": triggered_by,
            "started_at": start_time.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(duration, 1),
            "pages_requested": max_pages,
            "pages_completed": pages_completed,
            "awards_ingested": total_ingested,
            "errors_count": total_errors,
            "portal_total_archive": portal_total_archive,
            "recent_awards": recent_awards[:15]
        }

        self._persist_to_ledger(summary)

        if progress_callback:
            try:
                await progress_callback("cycle_completed", {
                    "domain": "awards",
                    "batch_id": batch_id,
                    "phase": "completed",
                    "processed_count": total_ingested,
                    "duration": duration,
                    "errors_count": total_errors,
                    "step_description": f"Phase 4 : Synchronisation terminée. {total_ingested} attributions enregistrées en {duration:.1f}s."
                })
            except Exception:
                pass

        logger.info(f"[{batch_id}] Finished awards sync: {total_ingested} awards ingested in {duration:.1f}s.")
        return summary
