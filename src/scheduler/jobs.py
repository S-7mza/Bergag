import asyncio
import logging
import argparse
import json
from pathlib import Path
from datetime import datetime
from src.database.session import async_session_factory
from src.scraper.client import PortalHttpClient
from src.scraper.listing_spider import ListingSpider
from src.scraper.detail_spider import DetailSpider
from src.scraper.ingestion_service import IngestionService
from src.profiles.loader import load_all_profiles
from src.engine.scoring_cascade import ScoringCascadeEngine
from src.alerts.email_dispatcher import EmailDispatcher
from src.alerts.webhook_dispatcher import WebhookDispatcher
from src.config.settings import settings
from sqlalchemy import select
from src.models.tender import Tender

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("CrawlerDaemon")

async def run_dry_run_validation(max_pages: int = 1, export_path: str = "data/dry_run_validation.json"):
    """
    Crawls active notices locally and validates parsing & scoring WITHOUT writing to DB.
    Allows inspection and validation of data quality before pushing to server database.
    """
    logger.info(f"=== DRY-RUN MODE: Crawling up to {max_pages} pages for local inspection ===")
    client = PortalHttpClient()
    listing_spider = ListingSpider(client)
    detail_spider = DetailSpider(client)
    scoring_engine = ScoringCascadeEngine()
    profiles = load_all_profiles()

    collected = []
    try:
        for page in range(1, max_pages + 1):
            logger.info(f"[DryRun] Fetching listing page {page}...")
            _, cards = await listing_spider.fetch_page(page=page, page_size=50)
            logger.info(f"[DryRun] Found {len(cards)} cards on page {page}.")

            for card in cards[:10]: # inspect first 10 per page
                portal_id = card.get("portal_id")
                if not portal_id:
                    continue
                
                _, detail_data = await detail_spider.fetch_detail(portal_id)
                scores = {}
                for profile in profiles:
                    res = await scoring_engine.evaluate_tender(detail_data, profile)
                    scores[profile.profile_name] = {
                        "score": round(res.overall_score, 1),
                        "verdict": res.decision_recommendation,
                        "line_items_matched": f"{len([m for m in res.line_item_matches if m.get('is_matched')])}/{len(res.line_item_matches)}"
                    }

                preview = {
                    "portal_id": portal_id,
                    "reference": detail_data.get("reference"),
                    "title": detail_data.get("title"),
                    "buyer": detail_data.get("buyer_name"),
                    "deadline": detail_data.get("deadline_at"),
                    "line_item_count": len(detail_data.get("line_items", [])),
                    "first_line_item": detail_data.get("line_items", [])[0] if detail_data.get("line_items") else None,
                    "profile_scores": scores
                }
                collected.append(preview)
                print(f"-> #{portal_id} [{preview['reference']}] {preview['title'][:55]}... | {preview['line_item_count']} items | Scores: {scores}")

    finally:
        await client.close()

    # Save to local inspection file
    out_file = Path(export_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(collected, f, indent=2, ensure_ascii=False)

    logger.info(f"=== DRY-RUN COMPLETE: Captured and evaluated {len(collected)} sample tenders. Saved to {export_path} ===")
    return collected

async def run_active_crawl_cycle(
    max_pages: int = 5, 
    send_emails: bool = True,
    progress_callback = None,
    is_aborted_callback = None
):
    """
    Executes an autonomous active BDC ingestion and alert cycle:
    1. Emits execution plan event.
    2. Crawls active listings at pageSize=50.
    3. Fetches detailed line items and stores immutable raw HTML snapshots.
    4. Runs 4-stage cascade scoring against all loaded company profiles.
    5. Dispatches responsive HTML Decision Cards via Gmail SMTP for GO offers.
    6. Emits BDC-by-BDC live ingestion events.
    """
    start_time = datetime.now()
    logger.info(f"Starting active BDC crawl and intelligence cycle (up to {max_pages} pages)...")

    if progress_callback:
        try:
            await progress_callback("plan_initialized", {
                "phase": "plan",
                "max_pages": max_pages,
                "estimated_tenders": max_pages * 50,
                "target_url": "https://www.marchespublics.gov.ma/bdc/entreprise/consultation/",
                "step_description": f"Phase 1 : Plan d'exécution validé. Scan ciblé de {max_pages} pages (~{max_pages * 50} BDC sur TGR)"
            })
        except Exception as e:
            logger.warning(f"Progress callback error: {e}")

    client = PortalHttpClient()
    scoring_engine = ScoringCascadeEngine()
    email_dispatcher = EmailDispatcher() if send_emails else None
    webhook_dispatcher = WebhookDispatcher()
    profiles = load_all_profiles()
    logger.info(f"Loaded {len(profiles)} company profiles: {[p.profile_name for p in profiles]}")

    processed_count = 0
    alerts_sent = 0
    first_portal_id = None
    last_portal_id = None

    try:
        async with async_session_factory() as session:
            service = IngestionService(session, client)

            # Fast-lookup ALL existing tenders in database (checks 1st, regardless of status)
            try:
                stmt_existing = select(Tender.portal_id)
                res_existing = await session.execute(stmt_existing)
                existing_portal_ids = {int(p) for p in res_existing.scalars().all() if p is not None}
            except Exception:
                existing_portal_ids = set()

            for page in range(1, max_pages + 1):
                if is_aborted_callback and is_aborted_callback():
                    logger.info("Crawl cycle aborted by operator at page loop.")
                    break
                try:
                    if progress_callback:
                        try:
                            await progress_callback("page_discovery", {
                                "phase": "discovery",
                                "page": page,
                                "max_pages": max_pages,
                                "step_description": f"Phase 2 : Scan de la page {page}/{max_pages} sur le portail des marchés publics..."
                            })
                        except Exception:
                            pass

                    raw_listing, cards = await service.listing_spider.fetch_page(page=page, page_size=50)
                    session.add(raw_listing)
                    await session.commit()

                    if not cards:
                        logger.info(f"Page {page} returned 0 cards. Reached end of active listing.")
                        break

                    if progress_callback:
                        try:
                            await progress_callback("cards_found", {
                                "phase": "discovery",
                                "page": page,
                                "cards_count": len(cards),
                                "cards": [
                                    {
                                        "portal_id": c.get("portal_id"),
                                        "reference": c.get("reference", f"#{c.get('portal_id')}"),
                                        "title": c.get("title", "Consultation BDC")[:60],
                                        "buyer": c.get("buyer_name", "Acheteur Public")
                                    }
                                    for c in cards if c.get("portal_id")
                                ],
                                "step_description": f"Phase 2 : {len(cards)} avis BDC détectés sur la page {page}. Début de l'ingestion unitaire..."
                            })
                        except Exception:
                            pass

                    for card in cards:
                        if is_aborted_callback and is_aborted_callback():
                            logger.info("Crawl cycle aborted by operator at card loop.")
                            break
                        portal_id = int(card.get("portal_id")) if card.get("portal_id") else None
                        if not portal_id:
                            continue

                        if first_portal_id is None:
                            first_portal_id = portal_id
                        last_portal_id = portal_id

                        # Check 1st: if tender is already in database, skip it (bring only non-existing IDs)
                        if portal_id in existing_portal_ids:
                            processed_count += 1
                            if progress_callback:
                                try:
                                    await progress_callback("bdc_ingested", {
                                        "phase": "bdc_item",
                                        "processed_count": processed_count,
                                        "portal_id": portal_id,
                                        "reference": card.get("reference", f"#{portal_id}"),
                                        "title": card.get("title", "Consultation BDC"),
                                        "buyer": card.get("buyer_name", "Acheteur Public"),
                                        "line_items_count": 0,
                                        "score": 0.0,
                                        "verdict": "EN_BASE",
                                        "step_description": f"Phase 3 : BDC #{portal_id} déjà en base (conforme, ignoré)."
                                    })
                                except Exception:
                                    pass
                            continue

                        # Check 1st directly against DB before calling network fetch
                        if await service.tender_exists(portal_id):
                            existing_portal_ids.add(portal_id)
                            processed_count += 1
                            continue

                        # Emit BDC loading event before fetching detail
                        if progress_callback:
                            try:
                                await progress_callback("bdc_loading", {
                                    "phase": "bdc_loading",
                                    "portal_id": portal_id,
                                    "reference": card.get("reference", f"#{portal_id}"),
                                    "title": card.get("title", "Consultation BDC")[:60],
                                    "buyer": card.get("buyer_name", "Acheteur Public"),
                                    "step_description": f"Phase 3 : Extraction fiche & devis BDC #{portal_id} : « {card.get('title', '')[:35]} »..."
                                })
                            except Exception:
                                pass

                        # Fetch detail and accordion line items
                        try:
                            raw_detail, detail_data = await service.detail_spider.fetch_detail(portal_id)
                            tender = await service.ingest_tender_detail(detail_data, raw_log=raw_detail)
                            await session.commit()
                            processed_count += 1
                            existing_portal_ids.add(portal_id)

                            # Evaluate against each profile
                            top_score = 0.0
                            top_verdict = "NO-GO"
                            for profile in profiles:
                                cascade_res = await scoring_engine.evaluate_tender(detail_data, profile)
                                if cascade_res.overall_score > top_score:
                                    top_score = cascade_res.overall_score
                                    top_verdict = cascade_res.decision_recommendation
                                
                                # If recommended GO (or Score >= alert_min_score), dispatch multi-channel alerts
                                is_high_fit = (
                                    cascade_res.decision_recommendation == "GO" 
                                    or cascade_res.overall_score >= settings.alert_min_score
                                )
                                if is_high_fit:
                                    logger.info(
                                        f"High-fit tender detected! #{portal_id} '{detail_data.get('title', '')[:40]}' "
                                        f"scored {cascade_res.overall_score:.0f}% for '{profile.profile_name}'."
                                    )
                                    # 1. Email notification
                                    if send_emails and settings.alert_enable_email and email_dispatcher:
                                        sent_mail = await email_dispatcher.send_decision_card(detail_data, cascade_res, profile)
                                        if sent_mail:
                                            alerts_sent += 1

                                    # 2. Webhook notification (Slack / MS Teams / WhatsApp / ERP)
                                    if settings.alert_enable_webhook:
                                        await webhook_dispatcher.send_notification(detail_data, cascade_res, profile)

                            if progress_callback:
                                try:
                                    await progress_callback("bdc_ingested", {
                                        "phase": "bdc_item",
                                        "portal_id": portal_id,
                                        "first_bdc_id": first_portal_id,
                                        "last_bdc_id": last_portal_id,
                                        "processed_count": processed_count,
                                        "estimated_total": max_pages * 50,
                                        "reference": detail_data.get("reference", ""),
                                        "title": detail_data.get("title", "")[:45],
                                        "buyer": detail_data.get("buyer_name", "Acheteur Public"),
                                        "line_items_count": len(detail_data.get("line_items", [])),
                                        "score": round(top_score, 1),
                                        "verdict": top_verdict,
                                        "step_description": f"Phase 3 : Ingestion BDC #{portal_id} : « {detail_data.get('title', '')[:35]} » ({len(detail_data.get('line_items', []))} articles) [{top_verdict}]"
                                    })
                                except Exception:
                                    pass

                        except Exception as e:
                            logger.error(f"Failed to process tender #{portal_id}: {e}")
                            await session.rollback()

                except Exception as e:
                    logger.error(f"Failed to crawl listing page {page}: {e}")
                    break

    finally:
        await client.close()

    duration = (datetime.now() - start_time).total_seconds()
    logger.info(
        f"Crawl cycle finished in {duration:.1f}s. "
        f"Processed {processed_count} tenders, dispatched {alerts_sent} email alerts."
    )

    if progress_callback:
        try:
            await progress_callback("cycle_completed", {
                "phase": "completed",
                "processed_count": processed_count,
                "first_bdc_id": first_portal_id,
                "last_bdc_id": last_portal_id,
                "duration": duration,
                "alerts_sent": alerts_sent,
                "step_description": f"Phase 4 : Lot terminé avec succès. {processed_count} BDC ingérés (#{first_portal_id or '—'} → #{last_portal_id or '—'}) en {duration:.1f}s"
            })
        except Exception:
            pass

async def run_historical_crawl_cycle(
    start_date: str,
    end_date: str = None,
    max_pages: int = 20,
    send_emails: bool = False,
    progress_callback = None,
    is_aborted_callback = None
):
    """
    Executes an autonomous historical procurement ingestion cycle for previous publication dates:
    1. Normalizes date window (start_date -> end_date).
    2. Emits execution plan event with matching publication filter.
    3. Crawls portal using dateMiseEnLigneStart & dateMiseEnLigneEnd filters at pageSize=50.
    4. Identifies already-ingested tenders to fast-skip redundant downloads.
    5. Ingests all missing historical consultations, accordion line items and executes scoring.
    6. Emits live BDC-by-BDC ingestion events for full operator visibility.
    """
    start_time = datetime.now()
    end_d = end_date or start_date
    logger.info(f"Starting historical BDC crawl cycle for period {start_date} -> {end_d} (up to {max_pages} pages)...")

    if progress_callback:
        try:
            await progress_callback("plan_initialized", {
                "phase": "plan",
                "max_pages": max_pages,
                "estimated_tenders": max_pages * 50,
                "target_url": f"https://www.marchespublics.gov.ma/bdc/entreprise/consultation/?dateStart={start_date}&dateEnd={end_d}",
                "step_description": f"Phase 1 : Plan validé. Rapatriement historique du {start_date} au {end_d} (~{max_pages * 50} BDC max)"
            })
        except Exception as e:
            logger.warning(f"Progress callback error: {e}")

    client = PortalHttpClient()
    scoring_engine = ScoringCascadeEngine()
    email_dispatcher = EmailDispatcher() if send_emails else None
    webhook_dispatcher = WebhookDispatcher()
    profiles = load_all_profiles()

    processed_count = 0
    alerts_sent = 0
    first_portal_id = None
    last_portal_id = None

    try:
        async with async_session_factory() as session:
            service = IngestionService(session, client)

            # Fast-lookup all existing portal_ids in database (checks 1st, regardless of status)
            try:
                stmt_existing = select(Tender.portal_id)
                res_existing = await session.execute(stmt_existing)
                existing_portal_ids = {int(p) for p in res_existing.scalars().all() if p is not None}
            except Exception:
                existing_portal_ids = set()

            for page in range(1, max_pages + 1):
                if is_aborted_callback and is_aborted_callback():
                    logger.info("Historical crawl cycle aborted by operator at page loop.")
                    break
                try:
                    if progress_callback:
                        try:
                            await progress_callback("page_discovery", {
                                "phase": "discovery",
                                "page": page,
                                "max_pages": max_pages,
                                "step_description": f"Phase 2 : Scan historique page {page}/{max_pages} ({start_date} → {end_d})..."
                            })
                        except Exception:
                            pass

                    raw_listing, cards, total_count = await service.listing_spider.fetch_by_date(
                        date_str=start_date,
                        end_date_str=end_d,
                        page=page,
                        page_size=50
                    )
                    session.add(raw_listing)
                    await session.commit()

                    if not cards:
                        logger.info(f"Historical page {page} returned 0 cards. Reached end of date range results.")
                        break

                    if progress_callback:
                        try:
                            await progress_callback("cards_found", {
                                "phase": "discovery",
                                "page": page,
                                "cards_count": len(cards),
                                "cards": [
                                    {
                                        "portal_id": c.get("portal_id"),
                                        "reference": c.get("reference", f"#{c.get('portal_id')}"),
                                        "title": c.get("title", "Consultation BDC")[:60],
                                        "buyer": c.get("buyer_name", "Acheteur Public")
                                    }
                                    for c in cards if c.get("portal_id")
                                ],
                                "step_description": f"Phase 2 : {len(cards)} avis BDC détectés sur la page {page} ({start_date} → {end_d}). Début ingestion..."
                            })
                        except Exception:
                            pass

                    for card in cards:
                        if is_aborted_callback and is_aborted_callback():
                            logger.info("Historical crawl cycle aborted by operator at card loop.")
                            break
                        portal_id = int(card.get("portal_id")) if card.get("portal_id") else None
                        if not portal_id:
                            continue

                        if first_portal_id is None:
                            first_portal_id = portal_id
                        last_portal_id = portal_id

                        # Check 1st: if tender is already in database, skip it (bring only non-existing IDs)
                        if portal_id in existing_portal_ids:
                            processed_count += 1
                            if progress_callback:
                                try:
                                    await progress_callback("bdc_ingested", {
                                        "phase": "bdc_item",
                                        "processed_count": processed_count,
                                        "portal_id": portal_id,
                                        "reference": card.get("reference", f"#{portal_id}"),
                                        "title": card.get("title", "Consultation BDC"),
                                        "buyer": card.get("buyer_name", "Acheteur Public"),
                                        "line_items_count": 0,
                                        "score": 0.0,
                                        "verdict": "EN_BASE",
                                        "step_description": f"Phase 3 : BDC #{portal_id} déjà indexé en base locale (ignoré)."
                                    })
                                except Exception:
                                    pass
                            continue

                        # Check 1st directly against DB before calling network fetch
                        if await service.tender_exists(portal_id):
                            existing_portal_ids.add(portal_id)
                            processed_count += 1
                            continue

                        # Emit BDC loading event before fetching detail
                        if progress_callback:
                            try:
                                await progress_callback("bdc_loading", {
                                    "phase": "bdc_loading",
                                    "portal_id": portal_id,
                                    "reference": card.get("reference", f"#{portal_id}"),
                                    "title": card.get("title", "Consultation BDC")[:60],
                                    "buyer": card.get("buyer_name", "Acheteur Public"),
                                    "step_description": f"Phase 3 : Extraction fiche & devis BDC #{portal_id} : « {card.get('title', '')[:35]} »..."
                                })
                            except Exception:
                                pass

                        # Fetch detail and accordion line items
                        try:
                            raw_detail, detail_data = await service.detail_spider.fetch_detail(portal_id)
                            tender = await service.ingest_tender_detail(detail_data, raw_log=raw_detail)
                            await session.commit()
                            processed_count += 1
                            existing_portal_ids.add(portal_id)

                            # Evaluate against each profile
                            top_score = 0.0
                            top_verdict = "NO-GO"
                            for profile in profiles:
                                cascade_res = await scoring_engine.evaluate_tender(detail_data, profile)
                                if cascade_res.overall_score > top_score:
                                    top_score = cascade_res.overall_score
                                    top_verdict = cascade_res.decision_recommendation
                                
                                is_high_fit = (
                                    cascade_res.decision_recommendation == "GO" 
                                    or cascade_res.overall_score >= settings.alert_min_score
                                )
                                if is_high_fit:
                                    if send_emails and settings.alert_enable_email and email_dispatcher:
                                        sent_mail = await email_dispatcher.send_decision_card(detail_data, cascade_res, profile)
                                        if sent_mail:
                                            alerts_sent += 1
                                    if settings.alert_enable_webhook:
                                        await webhook_dispatcher.send_notification(detail_data, cascade_res, profile)

                            if progress_callback:
                                try:
                                    await progress_callback("bdc_ingested", {
                                        "phase": "bdc_item",
                                        "portal_id": portal_id,
                                        "first_bdc_id": first_portal_id,
                                        "last_bdc_id": last_portal_id,
                                        "processed_count": processed_count,
                                        "estimated_total": max_pages * 50,
                                        "reference": detail_data.get("reference", ""),
                                        "title": detail_data.get("title", "")[:45],
                                        "buyer": detail_data.get("buyer_name", "Acheteur Public"),
                                        "line_items_count": len(detail_data.get("line_items", [])),
                                        "score": round(top_score, 1),
                                        "verdict": top_verdict,
                                        "step_description": f"Phase 3 : Ingestion BDC #{portal_id} : « {detail_data.get('title', '')[:35]} » ({len(detail_data.get('line_items', []))} articles) [{top_verdict}]"
                                    })
                                except Exception:
                                    pass

                        except Exception as e:
                            logger.error(f"Failed to process historical tender #{portal_id}: {e}")
                            await session.rollback()

                except Exception as e:
                    logger.error(f"Failed to crawl historical listing page {page}: {e}")
                    break

    finally:
        await client.close()

    duration = (datetime.now() - start_time).total_seconds()
    logger.info(
        f"Historical crawl cycle finished in {duration:.1f}s. "
        f"Processed {processed_count} tenders ({start_date} -> {end_d})."
    )

    if progress_callback:
        try:
            await progress_callback("cycle_completed", {
                "phase": "completed",
                "processed_count": processed_count,
                "first_bdc_id": first_portal_id,
                "last_bdc_id": last_portal_id,
                "duration": duration,
                "alerts_sent": alerts_sent,
                "step_description": f"Phase 4 : Lot historique terminé avec succès. {processed_count} BDC traités ({start_date} → {end_d}) en {duration:.1f}s"
            })
        except Exception:
            pass

async def wait_for_database_ready(max_retries: int = 30, retry_delay: float = 3.0):
    """
    Waits for the database to be reachable and migrations applied before starting the crawl.
    """
    logger.info("Checking database readiness and migrations...")
    for attempt in range(1, max_retries + 1):
        try:
            async with async_session_factory() as session:
                from sqlalchemy import text
                result = await session.execute(text("SELECT to_regclass('public.tenders');"))
                table_exists = result.scalar()
                if table_exists:
                    logger.info("Database connection healthy and schema tables detected.")
                    return True
                logger.info(f"Database reachable but migrations still pending (attempt {attempt}/{max_retries}). Waiting {retry_delay}s...")
        except Exception as e:
            logger.info(f"Database not ready yet ({e}) (attempt {attempt}/{max_retries}). Waiting {retry_delay}s...")
        await asyncio.sleep(retry_delay)
    
    logger.warning("Database readiness wait timed out. Proceeding anyway...")
    return False

async def run_daemon_loop(pages: int = 5, interval_seconds: int = 3600, send_emails: bool = True):
    """
    Runs the autonomous ingestion and alert pipeline continuously as a background daemon.
    """
    logger.info(f"Starting Bergag Crawler Daemon loop (interval: {interval_seconds}s, pages: {pages})...")
    await wait_for_database_ready()

    cycle_count = 0
    while True:
        cycle_count += 1
        logger.info(f"--- Starting Autonomous Crawl Cycle #{cycle_count} ---")
        try:
            await run_active_crawl_cycle(max_pages=pages, send_emails=send_emails)
        except Exception as e:
            logger.error(f"Error during crawl cycle #{cycle_count}: {e}", exc_info=True)

        logger.info(f"Cycle #{cycle_count} completed. Next scheduled cycle in {interval_seconds}s ({interval_seconds // 60}m)...")
        await asyncio.sleep(interval_seconds)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bergag Procurement Crawler & Ingestion Daemon")
    parser.add_argument("--pages", type=int, default=5, help="Number of listing pages to crawl (50 per page)")
    parser.add_argument("--dry-run", action="store_true", help="Crawl and score locally without writing to DB or sending email")
    parser.add_argument("--no-email", action="store_true", help="Save to DB but suppress Gmail alerts")
    parser.add_argument("--daemon", action="store_true", help="Run continuously in background daemon loop")
    parser.add_argument("--interval", type=int, default=3600, help="Interval between crawl cycles in seconds (default: 3600)")

    args = parser.parse_args()

    if args.dry_run:
        asyncio.run(run_dry_run_validation(max_pages=args.pages))
    elif args.daemon:
        asyncio.run(run_daemon_loop(pages=args.pages, interval_seconds=args.interval, send_emails=not args.no_email))
    else:
        asyncio.run(run_active_crawl_cycle(max_pages=args.pages, send_emails=not args.no_email))
