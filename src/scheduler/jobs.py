import asyncio
import logging
from datetime import datetime
from src.database.session import async_session_factory
from src.scraper.client import PortalHttpClient
from src.scraper.ingestion_service import IngestionService
from src.profiles.loader import load_all_profiles
from src.engine.scoring_cascade import ScoringCascadeEngine
from src.alerts.email_dispatcher import EmailDispatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("Scheduler")

async def run_active_crawl_cycle(max_pages: int = 5):
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
    email_dispatcher = EmailDispatcher()
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
                                if cascade_res.decision_recommendation == "GO" or cascade_res.overall_score >= 80.0:
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

if __name__ == "__main__":
    asyncio.run(run_active_crawl_cycle(max_pages=1))
