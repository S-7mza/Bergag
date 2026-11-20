import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from src.api.auth import User, require_role
from src.engine.batch_manager import batch_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/ingestion", tags=["Admin Ingestion Batches & Quality"])

class TriggerBatchRequest(BaseModel):
    pages: int = Field(default=2, ge=1, le=100, description="Nombre de pages de 50 avis à ingérer (jusqu'à 100 pages / 5000 avis)")
    send_emails: bool = Field(default=True, description="Expédier les alertes Gmail pour les offres GO")

class RemediateRequest(BaseModel):
    pages: int = Field(default=3, ge=1, le=100, description="Nombre de pages de rattrapage (jusqu'à 100 pages)")
    reason: Optional[str] = Field(default="Rattrapage diagnostique des lots manqués", description="Motif de l'opération")

class DateAuditReconcileRequest(BaseModel):
    date: str = Field(default="19/11/2026", description="Date ciblée ou date de début (DD/MM/YYYY)")
    end_date: Optional[str] = Field(default=None, description="Date de fin optionnelle pour plage (DD/MM/YYYY)")
    period_mode: str = Field(default="day", description="Mode de période ('day', 'range', 'month')")
    portal_ids: List[int] = Field(default_factory=list, description="Liste des identifiants BDC manquants à importer (ou vide pour auto-détection)")

class ActiveAuditReconcileRequest(BaseModel):
    portal_ids: List[int] = Field(default_factory=list, description="Liste des identifiants BDC actifs manquants à importer (ou vide pour auto-détection)")

class TriggerHistoricalBatchRequest(BaseModel):
    start_date: str = Field(description="Date de début (DD/MM/YYYY)")
    end_date: Optional[str] = Field(default=None, description="Date de fin optionnelle pour plage (DD/MM/YYYY)")
    period_mode: str = Field(default="range", description="Mode de période ('day', 'range', 'month')")
    pages: int = Field(default=20, ge=1, le=100, description="Nombre max de pages (50 avis/page, jusqu'à 100 pages)")
    send_emails: bool = Field(default=False, description="Expédier les alertes pour les avis historiques")

@router.get("/dashboard")
async def get_ingestion_dashboard(user: User = Depends(require_role(["admin", "analyst"]))):
    """
    Returns complete Ingestion Control Center state:
    1. Freshness SLA & 'Is Data Up To Date?' answer
    2. Data Quality Score per Category (Fournitures, Travaux, Services)
    3. Batches Ledger (Completed, In Progress, Missed, Pending)
    4. Diagnostic Gap Analysis with recommended one-click action
    5. Real-time Gap Probe between DB and live portal
    6. Date Exhaustiveness Audit for mathematical reconciliation
    """
    return await batch_manager.get_dashboard_state()

@router.get("/audit-date")
async def audit_date_exhaustiveness_endpoint(
    date: Optional[str] = Query(None, description="Date ou date de début (DD/MM/YYYY)"),
    end_date: Optional[str] = Query(None, description="Date de fin optionnelle (DD/MM/YYYY)"),
    mode: str = Query("day", description="Mode de sélection : 'day', 'range', 'month'"),
    force: bool = Query(False, description="Forcer une nouvelle interrogation en direct du portail TGR"),
    user: User = Depends(require_role(["admin", "analyst"]))
):
    """
    Performs a mathematical set reconciliation for a specific publication date, custom range, or full month:
    Compares the exact count and IDs of BDCs on the portal with the PostgreSQL database.
    """
    target = date or datetime.now().strftime("%d/%m/%Y")
    return await batch_manager.audit_date_exhaustiveness(
        target_date_str=target,
        end_date_str=end_date,
        period_mode=mode,
        fetch_live_portal=True,
        force_refresh=force
    )

@router.post("/audit-date/reconcile")
async def reconcile_missing_date_items(
    req: DateAuditReconcileRequest,
    user: User = Depends(require_role(["admin"]))
):
    """
    Directly pulls and ingests the specific missing BDC IDs for the audited date, range, or month.
    """
    return await batch_manager.remediate_missing_portal_ids(
        portal_ids=req.portal_ids,
        target_date_str=req.date,
        end_date_str=req.end_date,
        period_mode=req.period_mode,
        user_name=user.full_name
    )

@router.get("/audit-active")
async def audit_active_tenders_endpoint(
    force: bool = Query(False, description="Forcer une nouvelle interrogation en direct du portail TGR"),
    user: User = Depends(require_role(["admin", "analyst"]))
):
    """
    Audits active tenders exhaustiveness: guarantees that 100% of currently active consultations
    (submission deadline > now) on the public portal exist in the local database.
    """
    return await batch_manager.audit_active_tenders_coverage(force_refresh=force)

@router.post("/audit-active/reconcile")
async def reconcile_missing_active_items(
    req: Optional[ActiveAuditReconcileRequest] = None,
    user: User = Depends(require_role(["admin"]))
):
    """
    Directly targets and ingests missing active consultations so no business opportunity is lost.
    """
    p_ids = req.portal_ids if req else []
    return await batch_manager.reconcile_missing_active_tenders(
        portal_ids=p_ids,
        user_name=user.full_name
    )

@router.post("/probe-portal-gap")
async def probe_portal_gap(user: User = Depends(require_role(["admin", "analyst"]))):
    """
    Actively probes the public procurement portal website in real-time,
    compares the latest row in PostgreSQL with the newest published BDC online,
    and returns the exact count of missing rows and required batches.
    """
    return await batch_manager.probe_portal_gap(force_live_scan=True)

@router.get("/gap-analysis")
async def get_portal_gap_analysis(user: User = Depends(require_role(["admin", "analyst"]))):
    """
    Returns the latest computed gap analysis between local database and the portal.
    """
    return await batch_manager.probe_portal_gap(force_live_scan=False)

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

@router.post("/batches/trigger-historical")
async def trigger_historical_batch_endpoint(
    req: TriggerHistoricalBatchRequest,
    bg_tasks: BackgroundTasks,
    user: User = Depends(require_role(["admin"]))
):
    """
    Triggers an autonomous historical ingestion batch for previous publication dates (Admin only).
    Scans past dates/periods, fast-skips existing entries, and completes missing tenders.
    """
    if batch_manager.active_batch is not None:
        raise HTTPException(
            status_code=409,
            detail="Un lot d'ingestion est déjà en cours d'exécution. Veuillez patienter ou interrompre le lot actuel."
        )

    end_d = req.end_date or req.start_date
    bg_tasks.add_task(
        batch_manager.execute_historical_batch,
        start_date=req.start_date,
        end_date=end_d,
        max_pages=req.pages,
        period_mode=req.period_mode,
        trigger_type="historical",
        user_name=user.full_name,
        send_emails=req.send_emails
    )

    return {
        "status": "historical_batch_started",
        "message": f"⚡ Lot historique initié pour la période {req.start_date} → {end_d} (max {req.pages} pages / ~{req.pages * 50} BDC) par {user.full_name}."
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

@router.post("/batches/abort")
async def abort_active_batch(
    user: User = Depends(require_role(["admin"]))
):
    """
    Aborts the currently running ingestion batch immediately (Admin only).
    """
    return batch_manager.abort_active_batch(user_name=user.full_name)

