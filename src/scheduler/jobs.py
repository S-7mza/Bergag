import asyncio
import logging
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo
from src.database.session import async_session_factory
from src.scraper.client import PortalHttpClient
from src.scraper.listing_spider import ListingSpider
from src.scraper.detail_spider import DetailSpider
from src.scraper.ingestion_service import IngestionService
from src.profiles.loader import load_all_profiles, load_profile
from src.engine.scoring_cascade import ScoringCascadeEngine
from src.alerts.email_dispatcher import EmailDispatcher
from src.alerts.webhook_dispatcher import WebhookDispatcher
from src.config.settings import settings
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from src.models.tender import Tender, DailyAlertLog

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

async def run_awards_crawl_cycle(
    max_pages: int = 5,
    page_size: int = 50,
    date_start: str = None,
    date_end: str = None,
    progress_callback = None
):
    """
    Executes an autonomous awards synchronization cycle against the Moroccan
    Procurement results archive (/bdc/entreprise/consultation/resultat).
    """
    from src.ingestion.awards.pipeline import AwardsIngestionPipeline
    pipeline = AwardsIngestionPipeline()
    return await pipeline.run(
        max_pages=max_pages,
        page_size=page_size,
        date_start=date_start,
        date_end=date_end,
        progress_callback=progress_callback,
        triggered_by="Daemon / Scheduler"
    )

async def run_daily_digest_job(
    min_score: Optional[float] = None,
    digest_date: Optional[str] = None,
    session_factory=None,
    email_dispatcher: Optional[EmailDispatcher] = None,
) -> dict:
    """
    Collects all active, never-notified tenders with AI score >= min_score (default 70%)
    OR Cascade score >= min_score, sends a single consolidated HTML digest email,
    and records sent portal_ids in DailyAlertLog so future digests only include new offers.
    """
    threshold = float(min_score if min_score is not None else settings.alert_min_score)
    tz = ZoneInfo(settings.digest_timezone)
    today_str = digest_date or datetime.now(tz).strftime("%Y-%m-%d")
    now_utc = datetime.now(timezone.utc)
    sf = session_factory or async_session_factory
    dispatcher = email_dispatcher or EmailDispatcher()

    from src.engine.ai_diagnostician import AIAvisDiagnostician
    from src.engine.opportunity_xyz import fetch_market_context_for_tender

    try:
        target_profile = load_profile("software_data")
    except Exception:
        profiles = load_all_profiles()
        target_profile = profiles[0] if profiles else None

    scoring_engine = ScoringCascadeEngine()
    digest_items = []

    async with sf() as session:
        # 1. Fetch already-notified portal_ids
        sent_res = await session.execute(select(DailyAlertLog.portal_id))
        already_sent_ids = {int(pid) for pid in sent_res.scalars().all() if pid is not None}

        # 2. Fetch active tenders with deadline in the future
        stmt = (
            select(Tender)
            .options(selectinload(Tender.buyer), selectinload(Tender.line_items))
            .where(Tender.status == "active", Tender.deadline_at > now_utc)
            .order_by(Tender.deadline_at.asc())
        )
        tenders_res = await session.execute(stmt)
        active_tenders = tenders_res.scalars().all()

        for t in active_tenders:
            if t.portal_id in already_sent_ids:
                continue

            tender_dict = {
                "portal_id": t.portal_id,
                "reference": t.reference,
                "title": t.title,
                "buyer_name": t.buyer.official_name if t.buyer else "Acheteur Inconnu",
                "execution_location": t.execution_location or "Maroc",
                "main_category": t.main_category,
                "prestation_type": t.prestation_type,
                "status": t.status,
                "deadline_at": t.deadline_at.isoformat() if t.deadline_at else "",
                "line_items": [
                    {
                        "item_order": li.item_order,
                        "designation": li.designation,
                        "technical_specs": li.technical_specs,
                        "quantity": float(li.quantity) if li.quantity is not None else 1.0,
                        "unit": li.unit or "U",
                    }
                    for li in sorted(t.line_items, key=lambda x: x.item_order)
                ],
            }

            diag = AIAvisDiagnostician.diagnose_tender(tender_dict)
            ai_score = float(diag.matching_rate or 0.0)

            cascade_score = 0.0
            red_flags = []
            if target_profile is not None:
                cascade_res = await scoring_engine.evaluate_tender(tender_dict, target_profile)
                cascade_score = float(cascade_res.overall_score or 0.0)
                red_flags = list(cascade_res.red_flags or [])

            if ai_score < threshold and cascade_score < threshold:
                continue

            try:
                mkt = await fetch_market_context_for_tender(session, t)
                spent_ytd = mkt.get("buyer_spent_ytd_mad")
                headroom = max(0.0, 500000.0 - spent_ytd) if spent_ytd is not None else None
            except Exception:
                headroom = None

            digest_items.append({
                **tender_dict,
                "ai_score": ai_score,
                "cascade_score": cascade_score,
                "ai_domain": diag.primary_domain,
                "art91_headroom_mad": headroom,
                "red_flags": red_flags,
            })

        # Sort highest score first, then earliest deadline
        digest_items.sort(
            key=lambda x: (-max(x["ai_score"], x["cascade_score"]), x.get("deadline_at", ""))
        )

        if not digest_items:
            logger.info(f"[DailyDigest] 0 new active tenders >= {threshold:.0f}% for {today_str}.")
            return {"sent": False, "count": 0, "digest_date": today_str}

        sent_ok = await dispatcher.send_daily_digest(digest_items, digest_date=today_str, min_score=threshold)
        if sent_ok:
            for item in digest_items:
                session.add(DailyAlertLog(
                    portal_id=int(item["portal_id"]),
                    ai_score=round(float(item["ai_score"]), 2),
                    cascade_score=round(float(item["cascade_score"]), 2),
                    digest_date=today_str,
                    recipient_email=dispatcher.recipient,
                ))
            await session.commit()
            logger.info(f"[DailyDigest] Dispatched {len(digest_items)} new offers >= {threshold:.0f}% for {today_str}.")
        return {"sent": bool(sent_ok), "count": len(digest_items), "digest_date": today_str}


async def run_daemon_loop(pages: int = 5, interval_seconds: int = 3600, send_emails: bool = False):
    """
    Runs the autonomous ingestion, AI scoring, and 08:00 AM daily digest loop:
    - Every `interval_seconds` (default 1h): incremental crawl + post-ingestion AI scoring.
    - Daily at `settings.daily_sync_hour:daily_sync_minute` (default 07:30 Africa/Casablanca):
      full 100% active market sync + AI scoring.
    - Daily at `settings.daily_digest_hour:daily_digest_minute` (default 08:00 Africa/Casablanca):
      consolidated email digest of all NEW offers with AI/Cascade score >= 70%.
    """
    from src.engine.batch_manager import batch_manager

    logger.info(f"Starting Bergag Crawler Daemon loop (interval: {interval_seconds}s, pages: {pages})...")
    await wait_for_database_ready()

    tz = ZoneInfo(settings.digest_timezone)
    cycle_count = 0
    last_full_sync_date: Optional[str] = None
    last_digest_date: Optional[str] = None
    sleep_step = min(300, interval_seconds)  # Wake every 5 min to hit 07:30 / 08:00 accurately
    last_incremental_at: Optional[datetime] = None

    while True:
        now_local = datetime.now(tz)
        today_str = now_local.strftime("%Y-%m-%d")

        try:
            # 1. Daily 07:30 (or first run) 100% active market sync + automatic AI scoring
            sync_due = (
                last_full_sync_date != today_str
                and (
                    last_full_sync_date is None
                    or (now_local.hour, now_local.minute) >= (settings.daily_sync_hour, settings.daily_sync_minute)
                )
            )
            if sync_due and batch_manager.active_batch is None:
                logger.info(f"[Daemon] Running daily 100% active market sync + AI scoring ({today_str})...")
                await batch_manager.execute_active_sync_batch(user_name="Daemon Worker (Sync Quotidien 100%)")
                last_full_sync_date = today_str
                last_incremental_at = datetime.now(timezone.utc)

            # 2. Daily 08:00 AM consolidated digest email for NEW offers >= 70%
            digest_due = (
                last_digest_date != today_str
                and (now_local.hour, now_local.minute) >= (settings.daily_digest_hour, settings.daily_digest_minute)
            )
            if digest_due and settings.alert_enable_email:
                logger.info(f"[Daemon] Running 08:00 AM daily digest job (min_score={settings.alert_min_score}%)...")
                await run_daily_digest_job(min_score=settings.alert_min_score, digest_date=today_str)
                last_digest_date = today_str

            # 3. Hourly incremental crawl + AI scoring (no per-tender email spam)
            now_utc = datetime.now(timezone.utc)
            if (
                batch_manager.active_batch is None
                and (last_incremental_at is None or (now_utc - last_incremental_at).total_seconds() >= interval_seconds)
            ):
                cycle_count += 1
                logger.info(f"--- Starting Autonomous Incremental Crawl Cycle #{cycle_count} ---")
                await batch_manager.execute_batch(
                    pages=pages,
                    trigger_type="scheduled",
                    user_name="Daemon Worker",
                    send_emails=send_emails,
                )
                last_incremental_at = datetime.now(timezone.utc)
        except Exception as e:
            logger.error(f"Error during daemon loop: {e}", exc_info=True)

        await asyncio.sleep(sleep_step)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bergag Procurement Crawler & Ingestion Daemon")
    parser.add_argument("--pages", type=int, default=5, help="Number of listing pages to crawl (50 per page)")
    parser.add_argument("--dry-run", action="store_true", help="Crawl and score locally without writing to DB or sending email")
    parser.add_argument("--no-email", action="store_true", help="Save to DB but suppress Gmail alerts")
    parser.add_argument("--offline", action="store_true", help="Collect data locally and generate portable JSON bundle in data/offline_exports/ (no database required)")
    parser.add_argument("--output", type=str, default=None, help="Custom file path for offline export package")
    parser.add_argument("--awards", action="store_true", help="Crawl historical awards & results instead of active BDC notices")
    parser.add_argument("--date-start", type=str, default=None, help="Start date for awards crawl (DD/MM/YYYY)")
    parser.add_argument("--date-end", type=str, default=None, help="End date for awards crawl (DD/MM/YYYY)")
    parser.add_argument("--daemon", action="store_true", help="Run continuously in background daemon loop")
    parser.add_argument("--digest", action="store_true", help="Run the 08:00 AM daily digest email job immediately")
    parser.add_argument("--interval", type=int, default=3600, help="Interval between crawl cycles in seconds (default: 3600)")

    args = parser.parse_args()

    if args.dry_run:
        asyncio.run(run_dry_run_validation(max_pages=args.pages))
    elif args.offline:
        from src.ingestion.offline.exporter import OfflineExporter
        exporter = OfflineExporter()
        if args.awards:
            asyncio.run(exporter.collect_awards(
                max_pages=args.pages,
                date_start=args.date_start,
                date_end=args.date_end,
                output_path=args.output
            ))
        else:
            asyncio.run(exporter.collect_bdc(
                max_pages=args.pages,
                output_path=args.output
            ))
    elif args.awards:
        asyncio.run(run_awards_crawl_cycle(max_pages=args.pages, date_start=args.date_start, date_end=args.date_end))
    elif args.digest:
        asyncio.run(run_daily_digest_job())
    elif args.daemon:
        asyncio.run(run_daemon_loop(pages=args.pages, interval_seconds=args.interval, send_emails=False))
    else:
        asyncio.run(run_active_crawl_cycle(max_pages=args.pages, send_emails=not args.no_email))
