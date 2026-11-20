import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.routes.feed import router as feed_router
from src.api.routes.analytics import router as analytics_router
from src.api.routes.auth import router as auth_router
from src.api.routes.crawler import router as crawler_router
from src.api.routes.batches import router as batches_router

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

# Mount static files directory if present
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

def load_dashboard_html() -> str:
    """Loads dashboard HTML from templates directory with fallback"""
    template_path = TEMPLATES_DIR / "index.html"
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    return "<html><body><h1>Dashboard template not found</h1></body></html>"

# Cached template content for high performance and backward compatibility
HTML_DASHBOARD = load_dashboard_html()

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serves the single-page responsive procurement dashboard with RBAC and Chart.js"""
    return HTMLResponse(content=HTML_DASHBOARD)
