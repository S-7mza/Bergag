import logging
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.og_preview import generate_og_image, render_og_meta_tags
from src.database.session import get_db_session
from src.models.tender import Tender

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

from src.config.settings import settings

_allowed_origins = list(dict.fromkeys([
    settings.app_url.rstrip("/"),
    "https://bergag.nexenflow.com",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response

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


def _get_public_base_url(request: Request) -> str:
    """Resolves public base URL respecting reverse-proxy headers (Cloudflare / Nginx)."""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if host:
        return f"{proto}://{host}".rstrip("/")
    return str(request.base_url).rstrip("/")


async def _resolve_tender_og_info(portal_id: int, session: AsyncSession) -> Optional[Dict[str, Any]]:
    """Fetches tender metadata + AI match info for Open Graph link previews."""
    from src.engine.ai_matching_agent import ai_matching_agent

    tender = None
    try:
        stmt = (
            select(Tender)
            .options(selectinload(Tender.buyer))
            .where(Tender.portal_id == portal_id)
        )
        res = await session.execute(stmt)
        tender = res.scalar_one_or_none()
    except Exception as e:
        logger.debug(f"OG lookup DB fallback for #{portal_id}: {e}")

    cached_diag = ai_matching_agent.get_cached_diagnosis(portal_id)

    if tender:
        dl_str = "En cours"
        if tender.deadline_at:
            dl_str = tender.deadline_at.strftime("%d/%m/%Y %H:%M")
        return {
            "portal_id": tender.portal_id,
            "reference": tender.reference,
            "source_type": tender.source_type,
            "title": tender.title,
            "buyer_name": tender.buyer.official_name if tender.buyer else "Acheteur Public",
            "execution_location": tender.execution_location or "Maroc",
            "deadline_display": dl_str,
            "matching_rate": cached_diag.matching_rate if cached_diag else None,
            "primary_domain": cached_diag.primary_domain if cached_diag else "",
            "verdict": cached_diag.verdict if cached_diag else "",
            "hardware_dependency": cached_diag.hardware_dependency if cached_diag else "",
            "detected_technologies": cached_diag.detected_technologies if cached_diag else [],
        }

    if cached_diag:
        return {
            "portal_id": portal_id,
            "reference": f"#{portal_id}",
            "source_type": "BDC",
            "title": cached_diag.diagnostic_summary[:140],
            "buyer_name": "Marchés Publics Maroc",
            "execution_location": "Maroc",
            "deadline_display": "Voir fiche",
            "matching_rate": cached_diag.matching_rate,
            "primary_domain": cached_diag.primary_domain,
            "verdict": cached_diag.verdict,
            "hardware_dependency": cached_diag.hardware_dependency,
            "detected_technologies": cached_diag.detected_technologies,
        }

    return None


def _inject_og_meta(html_content: str, og_tags: str) -> str:
    placeholder = "<!-- OG_META_PLACEHOLDER -->"
    if placeholder in html_content:
        return html_content.replace(placeholder, og_tags, 1)
    return html_content.replace("</head>", f"    {og_tags}\n</head>", 1)


@app.get("/og-image.png", include_in_schema=False)
async def get_default_og_image():
    """Returns a 1200x630 PNG preview image for the main Bergag dashboard."""
    png_bytes = generate_og_image()
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/og-image/avis/{portal_id}.png", include_in_schema=False)
async def get_avis_og_image(portal_id: int, session: AsyncSession = Depends(get_db_session)):
    """Returns a 1200x630 PNG preview card for a specific avis/tender."""
    tender_info = await _resolve_tender_og_info(portal_id, session)
    png_bytes = generate_og_image(tender_info)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=1800"},
    )


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(
    request: Request,
    tender: Optional[int] = Query(default=None, description="Optional portal_id for OG preview & deep-link"),
    session: AsyncSession = Depends(get_db_session),
):
    """Serves the single-page responsive procurement dashboard with dynamic Open Graph tags."""
    base_url = _get_public_base_url(request)
    tender_info = await _resolve_tender_og_info(tender, session) if tender else None
    page_url = f"{base_url}/?tender={tender}" if tender else f"{base_url}/"
    og_tags = render_og_meta_tags(base_url, tender_info=tender_info, page_url=page_url)
    return HTMLResponse(content=_inject_og_meta(load_dashboard_html(), og_tags))


@app.get("/avis/{portal_id}", response_class=HTMLResponse)
async def serve_avis_deep_link(
    portal_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    """Serves the dashboard with tender-specific Open Graph tags for WhatsApp/social sharing."""
    base_url = _get_public_base_url(request)
    tender_info = await _resolve_tender_og_info(portal_id, session)
    page_url = f"{base_url}/avis/{portal_id}"
    og_tags = render_og_meta_tags(base_url, tender_info=tender_info, page_url=page_url)
    return HTMLResponse(content=_inject_og_meta(load_dashboard_html(), og_tags))
