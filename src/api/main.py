import logging
from pathlib import Path
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.routes.feed import router as feed_router
from src.api.routes.analytics import router as analytics_router
from src.api.routes.auth import router as auth_router
from src.api.routes.crawler import router as crawler_router
from src.api.routes.batches import router as batches_router
from src.api.routes.awards_ingestion import router as awards_ingestion_router
from src.api.routes.offline_ingestion import router as offline_ingestion_router
from src.api.routes.agent_diagnostics import router as agent_diagnostics_router
from src.api.routes.tuner import router as tuner_router

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Antigravity Procurement Intelligence",
    description="Autonomous Moroccan Public Procurement (BDC & AO) Intelligence Engine with RBAC",
    version="2.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route registrations
app.include_router(auth_router)
app.include_router(crawler_router)
app.include_router(feed_router)
app.include_router(analytics_router)
app.include_router(batches_router)
app.include_router(awards_ingestion_router)
app.include_router(offline_ingestion_router)
app.include_router(agent_diagnostics_router)
app.include_router(tuner_router)

# Mount static files directory if present
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.on_event("startup")
async def on_startup_sync_ai_matches():
    """
    Automatic update hooks:
    1. Runs background AI diagnosis sync on startup.
    2. Starts the fault-tolerant autonomous ingestion scheduler (hourly incremental + daily 100% sync).
    """
    import asyncio
    import os
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    asyncio.create_task(_background_db_matching_sync())
    asyncio.create_task(_autonomous_ingestion_scheduler())


async def _run_scheduled_check_once():
    """
    Single evaluation pass of the autonomous ingestion scheduler:
    - Guarantees at least 1 full 100% active market sync every 24h.
    - Guarantees an hourly incremental ingestion batch (pages=5) if no worker ran recently.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import desc, select
    from src.database.session import async_session_factory
    from src.engine.batch_manager import batch_manager
    from src.models.batch import IngestionBatch

    if batch_manager.active_batch is not None:
        return "busy"

    now = datetime.now()
    last_full_sync: datetime | None = None
    last_any_batch: datetime | None = None

    # Check both in-memory ledger and PostgreSQL for latest completed batches (coordinates with mp_worker)
    try:
        async with async_session_factory() as session:
            res_full = await session.execute(
                select(IngestionBatch.completed_at)
                .where(
                    IngestionBatch.trigger_type == "active_sync_100_pct",
                    IngestionBatch.status == "completed",
                )
                .order_by(desc(IngestionBatch.completed_at))
                .limit(1)
            )
            last_full_sync = res_full.scalar_one_or_none()

            res_any = await session.execute(
                select(IngestionBatch.completed_at)
                .where(IngestionBatch.status == "completed")
                .order_by(desc(IngestionBatch.completed_at))
                .limit(1)
            )
            last_any_batch = res_any.scalar_one_or_none()
    except Exception as e:
        logger.debug(f"[AutoScheduler] DB check fallback to memory ledger: {e}")

    # Fallback to in-memory ledger timestamps if DB had none
    for b in reversed(batch_manager.batches):
        if b.status == "completed" and b.completed_at:
            if b.trigger_type == "active_sync_100_pct" and (last_full_sync is None or b.completed_at > last_full_sync):
                last_full_sync = b.completed_at
            if last_any_batch is None or b.completed_at > last_any_batch:
                last_any_batch = b.completed_at

    # Normalize naive comparison
    if last_full_sync and last_full_sync.tzinfo is not None:
        last_full_sync = last_full_sync.replace(tzinfo=None)
    if last_any_batch and last_any_batch.tzinfo is not None:
        last_any_batch = last_any_batch.replace(tzinfo=None)

    if last_full_sync is None or (now - last_full_sync) >= timedelta(hours=24):
        logger.info("[AutoScheduler] Triggering daily 100% active market sync for all missing avis...")
        await batch_manager.execute_active_sync_batch(user_name="Système (Sync Quotidien 100%)")
        return "daily_full_sync"

    if last_any_batch is None or (now - last_any_batch) >= timedelta(minutes=55):
        logger.info("[AutoScheduler] Triggering hourly scheduled incremental batch (5 pages)...")
        await batch_manager.execute_batch(pages=5, trigger_type="scheduled", user_name="Système (Auto)")
        return "hourly_batch"

    return "up_to_date"


async def _autonomous_ingestion_scheduler():
    """Background loop inside web app ensuring automatic batches run even if mp_worker is offline."""
    import asyncio
    await asyncio.sleep(45)  # Allow DB & app startup to settle
    while True:
        try:
            await _run_scheduled_check_once()
        except Exception as e:
            logger.warning(f"[AutoScheduler] Scheduled check error: {e}")
        await asyncio.sleep(900)  # Check every 15 minutes

async def _background_db_matching_sync():
    from src.database.session import async_session_factory
    from src.engine.ai_matching_agent import ai_matching_agent
    try:
        async with async_session_factory() as session:
            logger.info("Auto-sync: Starting background avis AI diagnosis and DB matching update...")
            report = await ai_matching_agent.sync_avis_diagnoses_to_db(
                session=session,
                profile_name="software_data",
                limit=2500,
                force_refresh=False
            )
            logger.info(
                f"Auto-sync completed: {report['total_scanned']} avis scanned, "
                f"{report['matches_created']} created, {report['matches_updated']} updated in DB."
            )
    except Exception as e:
        logger.debug(f"Startup DB matching sync deferred (database offline/busy): {e}")

# Template loader (dynamic reload to reflect template edits immediately)
def load_dashboard_html() -> str:
    """Loads dashboard HTML from templates directory with fallback"""
    template_path = TEMPLATES_DIR / "index.html"
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    return "<html><body><h1>Dashboard template not found</h1></body></html>"

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Returns empty 204 for browser favicon probe to avoid 404 noise"""
    return Response(status_code=204)

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serves the single-page responsive procurement dashboard with RBAC and Chart.js"""
    return HTMLResponse(content=load_dashboard_html())
