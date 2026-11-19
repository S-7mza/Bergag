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

async def run_active_crawl_cycle(max_pages: int = 5, send_emails: bool = True):
    """
    Executes an autonomous active BDC ingestion and alert cycle:
    1. Crawls active listings at pageSize=50.
    2. Fetches detailed line items and stores immutable raw HTML snapshots.
    3. Runs 4-stage cascade scoring against all loaded company profiles.
    4. Dispatches responsive HTML Decision Cards via Gmail SMTP for GO offers.
    """
    start_time = datetime.now()
    logger.info(f"Starting active BDC crawl and intelligence cycle (up to {max_pages} pages)...")

    client = PortalHttpClient()
    scoring_engine = ScoringCascadeEngine()
    email_dispatcher = EmailDispatcher() if send_emails else None
    profiles = load_all_profiles()
    logger.info(f"Loaded {len(profiles)} company profiles: {[p.profile_name for p in profiles]}")

    processed_count = 0
    alerts_sent = 0

    try:
        async with async_session_factory() as session:
            service = IngestionService(session, client)

            for page in range(1, max_pages + 1):
                try:
                    raw_listing, cards = await service.listing_spider.fetch_page(page=page, page_size=50)
                    session.add(raw_listing)
                    await session.commit()

                    if not cards:
                        logger.info(f"Page {page} returned 0 cards. Reached end of active listing.")
                        break

                    for card in cards:
                        portal_id = card.get("portal_id")
                        if not portal_id:
                            continue

                        # Fetch detail and accordion line items
                        try:
                            raw_detail, detail_data = await service.detail_spider.fetch_detail(portal_id)
                            tender = await service.ingest_tender_detail(detail_data, raw_log=raw_detail)
                            await session.commit()
                            processed_count += 1

                            # Evaluate against each profile
                            for profile in profiles:
                                cascade_res = await scoring_engine.evaluate_tender(detail_data, profile)
                                
                                # If recommended GO (Score >= 80%), dispatch email alert
                                if send_emails and (cascade_res.decision_recommendation == "GO" or cascade_res.overall_score >= 80.0):
                                    logger.info(
                                        f"High-fit tender detected! #{portal_id} '{detail_data.get('title')[:40]}' "
                                        f"scored {cascade_res.overall_score:.0f}% for '{profile.profile_name}'. Sending email..."
                                    )
                                    sent = await email_dispatcher.send_decision_card(detail_data, cascade_res, profile)
                                    if sent:
                                        alerts_sent += 1

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
