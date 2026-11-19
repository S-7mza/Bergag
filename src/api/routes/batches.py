import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from src.api.auth import User, require_role
from src.engine.batch_manager import batch_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/ingestion", tags=["Admin Ingestion Batches & Quality"])

class TriggerBatchRequest(BaseModel):
    pages: int = Field(default=2, ge=1, le=10, description="Nombre de pages de 50 avis à ingérer")
    send_emails: bool = Field(default=True, description="Expédier les alertes Gmail pour les offres GO")

class RemediateRequest(BaseModel):
    pages: int = Field(default=3, ge=1, le=10, description="Nombre de pages de rattrapage")
    reason: Optional[str] = Field(default="Rattrapage diagnostique des lots manqués", description="Motif de l'opération")

@router.get("/dashboard")
async def get_ingestion_dashboard(user: User = Depends(require_role(["admin", "analyst"]))):
    """
    Returns complete Ingestion Control Center state:
    1. Freshness SLA & 'Is Data Up To Date?' answer
    2. Data Quality Score per Category (Fournitures, Travaux, Services)
    3. Batches Ledger (Completed, In Progress, Missed, Pending)
    4. Diagnostic Gap Analysis with recommended one-click action
    """
    return await batch_manager.get_dashboard_state()

@router.post("/remediate")
async def trigger_diagnostic_remediation(
    req: RemediateRequest,
    bg_tasks: BackgroundTasks,
    user: User = Depends(require_role(["admin"]))
):
    """
    Executes the recommended diagnostic remediation action immediately (Admin only).
    Combles the detected data gaps, missed batches, and un-ingested active notices.
    """
    if batch_manager.active_batch is not None:
        raise HTTPException(
            status_code=409, 
            detail="Un lot d'ingestion est déjà en cours d'exécution. Veuillez patienter."
        )

    # Launch in background
    bg_tasks.add_task(
        batch_manager.execute_batch,
        pages=req.pages,
        trigger_type="diagnostic_remediation",
        user_name=user.full_name
    )

    return {
        "status": "remediation_started",
        "message": f"⚡ Action de rattrapage lancée ({req.pages} pages) par {user.full_name}.",
        "estimated_duration_seconds": req.pages * 6
    }

@router.post("/batches/trigger")
async def trigger_custom_batch(
    req: TriggerBatchRequest,
    bg_tasks: BackgroundTasks,
    user: User = Depends(require_role(["admin"]))
):
    """
    Triggers an on-demand ingestion batch with custom page depth (Admin only).
    """
    if batch_manager.active_batch is not None:
        raise HTTPException(
            status_code=409,
            detail="Un lot d'ingestion est déjà en cours d'exécution."
        )

    bg_tasks.add_task(
        batch_manager.execute_batch,
        pages=req.pages,
        trigger_type="manual",
        user_name=user.full_name
    )

    return {
        "status": "batch_started",
        "message": f"Lot d'ingestion manuel initié pour {req.pages} pages par {user.full_name}."
    }

@router.post("/batches/{batch_id}/retry")
async def retry_missed_or_failed_batch(
    batch_id: str,
    bg_tasks: BackgroundTasks,
    user: User = Depends(require_role(["admin"]))
):
    """
    Retries a missed, failed or partial batch (Admin only).
    """
    target = next((b for b in batch_manager.batches if b.batch_id == batch_id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Lot '{batch_id}' introuvable.")

    if batch_manager.active_batch is not None:
        raise HTTPException(status_code=409, detail="Un autre lot est déjà en cours d'exécution.")

    bg_tasks.add_task(
        batch_manager.execute_batch,
        pages=target.pages_requested or 2,
        trigger_type="manual",
        user_name=user.full_name
    )

    return {
        "status": "retry_started",
        "message": f"Relance du lot {batch_id} enclenchée par {user.full_name}."
    }
