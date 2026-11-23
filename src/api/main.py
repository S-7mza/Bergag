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

# Mount static files directory if present
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.on_event("startup")
async def on_startup_sync_ai_matches():
    """
    Automatic update hook:
    Whenever the application boots or code updates are pushed in Antigravity,
    runs a background task to loop on the avis, diagnose each offer deeply without
    external APIs, and update matching rates directly in the PostgreSQL database.
    """
    import asyncio
    asyncio.create_task(_background_db_matching_sync())

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
