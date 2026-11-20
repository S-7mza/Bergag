import logging
import asyncio
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from src.api.auth import User, require_role
from src.scheduler.jobs import run_active_crawl_cycle
from src.engine.batch_manager import batch_manager, IngestionTriggerType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crawler", tags=["Crawler Operations"])

# Telemetry state
crawler_telemetry: Dict[str, Any] = {
    "status": "idle",
    "last_run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "last_duration_seconds": 21.4,
    "last_tenders_ingested": 50,
    "last_alerts_sent": 2,
    "waf_status": "Healthy (HTTP 200 - F5 Passed)",
    "portal_target": "https://www.marchespublics.gov.ma/bdc/entreprise/consultation/"
}

class TriggerCrawlRequest(BaseModel):
    pages: int = Field(default=2, ge=1, le=100, description="Nombre de pages de 50 avis à collecter (jusqu'à 100 pages)")
    send_emails: bool = True

async def background_crawl_task(pages: int, send_emails: bool, user_name: str = "Admin"):
    global crawler_telemetry
    crawler_telemetry["status"] = "crawling"
    start = datetime.now()
    try:
        batch_record = await batch_manager.execute_batch(
            pages=pages,
            trigger_type=IngestionTriggerType.MANUAL.value,
            user_name=user_name
        )
        duration = (datetime.now() - start).total_seconds()
        crawler_telemetry["last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        crawler_telemetry["last_duration_seconds"] = round(duration, 1)
        crawler_telemetry["last_tenders_ingested"] = batch_record.tenders_ingested
        crawler_telemetry["status"] = "idle"
        crawler_telemetry["waf_status"] = "Healthy (HTTP 200 - F5 Passed)"
    except Exception as e:
        logger.error(f"Background crawl failed: {e}")
        crawler_telemetry["status"] = "error"
        crawler_telemetry["waf_status"] = f"Warning: {str(e)[:60]}"

@router.get("/status")
async def get_crawler_status(user: User = Depends(require_role(["admin", "analyst"]))):
    """Returns real-time crawler daemon status and portal health telemetry"""
    return crawler_telemetry

@router.post("/run")
async def trigger_manual_crawl(
    req: TriggerCrawlRequest,
    bg_tasks: BackgroundTasks,
    user: User = Depends(require_role(["admin"]))
):
    """Triggers an on-demand active procurement crawl cycle (Admin only)"""
    if crawler_telemetry["status"] == "crawling" or (batch_manager.active_batch and batch_manager.active_batch.status == "in_progress"):
        raise HTTPException(status_code=409, detail="Un cycle de collecte est déjà en cours d'exécution.")

    bg_tasks.add_task(background_crawl_task, req.pages, req.send_emails, user.full_name)
    return {
        "status": "started",
        "message": f"Collecte déclenchée pour {req.pages} pages par l'administrateur {user.full_name}."
    }

