import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db_session
from src.engine.ai_matching_agent import ai_matching_agent
from src.engine.ai_diagnostician import AIMatchingDiagnosis
from src.engine.antigravity_study import antigravity_study_manager, AntigravityStudyRecord
from src.engine.cps_extractor import CPSDeterministicExtractor
from src.engine.scoring_cascade import invalidate_tender_cache
from src.models.tender import Tender
from src.api.schemas import DiagnoseBatchRequest, DiagnoseBatchResponse
from src.api.auth import User, get_current_user, require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["AI Matching Agent"])

@router.get("/diagnose/{portal_id}", response_model=AIMatchingDiagnosis)
async def diagnose_single_avis_endpoint(
    portal_id: int,
    force_refresh: bool = Query(False, description="Re-run deep diagnostic even if cached"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Agent Deep Inspection: Examines an avis notice deeply (title, category,
    specifications, and line items) and returns an in-depth AI matching diagnosis
    for the Programming, Web, Data & AI profile.
    """
    try:
        diagnosis = await ai_matching_agent.diagnose_single_avis(
            portal_id=portal_id,
            session=session,
            force_refresh=force_refresh
        )
        return diagnosis
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error diagnosing tender #{portal_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Diagnostic error: {str(e)}")

@router.post("/diagnose-batch", response_model=DiagnoseBatchResponse)
async def diagnose_batch_avis_endpoint(
    request: DiagnoseBatchRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_role(["admin", "analyst"]))
):
    """
    Agent Avis-After-Avis Batch Runner:
    Iterates through notices ('avis après avis'), diagnoses each offer deeply,
    computes the specialized AI Matching Rate, and generates an aggregate report.
    """
    try:
        report = await ai_matching_agent.diagnose_batch(
            session=session,
            limit=request.limit,
            open_only=request.open_only,
            force_refresh=request.force_refresh
        )
        return DiagnoseBatchResponse(
            success=True,
            total_scanned=report["total_scanned"],
            rating_distribution=report["rating_distribution"],
            domain_distribution=report["domain_distribution"],
            top_technologies=report["top_technologies"],
            top_opportunities=report["top_opportunities"]
        )
    except Exception as e:
        logger.error(f"Batch diagnosis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch diagnosis error: {str(e)}")

@router.get("/diagnostics/report")
async def get_diagnostics_report(
    limit: int = Query(250, ge=1, le=1000),
    open_only: bool = Query(False),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Returns the comprehensive diagnostic report of all evaluated avis,
    highlighting the top software, web, and data opportunities in the Moroccan public market.
    """
    report = await ai_matching_agent.diagnose_batch(
        session=session,
        limit=limit,
        open_only=open_only,
        force_refresh=False
    )
    return {
        "success": True,
        "report": report
    }

@router.post("/sync-db")
async def sync_avis_diagnoses_to_database(
    limit: int = Query(2500, ge=1, le=5000, description="Max tenders to diagnose and sync"),
    force_refresh: bool = Query(False, description="Whether to re-evaluate cached entries"),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_role(["admin"]))
):
    """
    Direct Database Sync:
    Loops on all avis notices, deeply reads each tender's line-item specifications,
    computes the AI Matching Rate locally without external APIs, and directly updates
    the 'profile_matches' and 'company_profiles' tables in PostgreSQL.
    """
    try:
        result = await ai_matching_agent.sync_avis_diagnoses_to_db(
            session=session,
            profile_name="software_data",
            limit=limit,
            force_refresh=force_refresh
        )
        return {
            "success": True,
            "message": (
                f"Synchronisation terminée : {result['total_scanned']} avis diagnostiqués, "
                f"{result['matches_created']} créés, {result['matches_updated']} mis à jour en base de données."
            ),
            "data": result
        }
    except Exception as e:
        logger.error(f"Error syncing diagnoses to database: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database sync error: {str(e)}")


class AntigravityStudyInput(BaseModel):
    verdict: str = Field(..., pattern="^(GO|CONSIDER|NO-GO)$")
    priority_tier: str = Field(default="P2", pattern="^(P1|P2|P3|ARCHIVE)$")
    opportunity_score: float = Field(..., ge=0.0, le=100.0)
    technical_fit_x: float = Field(default=0.0, ge=0.0, le=100.0)
    commercial_value_y: float = Field(default=0.0, ge=0.0, le=100.0)
    win_probability_z: float = Field(default=0.0, ge=0.0, le=100.0)
    why_reasons: List[str] = Field(default_factory=list)
    cps_findings: Dict[str, Any] = Field(default_factory=dict)
    bid_strategy: str = Field(default="")
    custom_prompt_used: Optional[str] = None


class AntigravityBatchInput(BaseModel):
    studies: List[AntigravityStudyRecord]


@router.get("/antigravity/pending")
async def get_pending_antigravity_studies(
    limit: int = Query(25, ge=1, le=200),
    include_studied: bool = Query(False, description="Include already studied avis"),
    fetch_attachments: bool = Query(False, description="Pre-download missing .zip attachments before CPS extraction"),
    sort_by: str = Query("ai_score_desc", description="Order queue by 'ai_score_desc' (default) or 'deadline_asc'"),
    min_ai_score: float = Query(0.0, ge=0.0, le=100.0, description="Minimum AI matching rate filter"),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_role(["admin", "analyst"])),
):
    """
    Exports active avis with line items, extracted CPS text, and Y/Z market context
    ordered by highest AI score first (by default) so Antigravity studies top opportunities first.
    """
    from pathlib import Path
    from src.engine.ai_diagnostician import AIAvisDiagnostician
    from src.engine.opportunity_xyz import fetch_market_context_for_tender

    now = datetime.now(timezone.utc)
    pool_cap = 2500 if sort_by == "ai_score_desc" else limit * 3
    stmt = (
        select(Tender)
        .options(selectinload(Tender.buyer), selectinload(Tender.line_items))
        .where(Tender.status == "active", Tender.deadline_at > now)
        .order_by(Tender.deadline_at.asc())
        .limit(pool_cap)
    )
    res = await session.execute(stmt)
    tenders = res.scalars().all()

    studied_ids = antigravity_study_manager.list_studied_ids()
    candidates = []
    for t in tenders:
        if not include_studied and t.portal_id in studied_ids:
            continue

        cached_diag = ai_matching_agent.get_cached_diagnosis(t.portal_id)
        if cached_diag is not None:
            ai_rate = float(cached_diag.matching_rate or 0.0)
            ai_domain = cached_diag.primary_domain
        else:
            quick_dict = {
                "portal_id": t.portal_id,
                "reference": t.reference,
                "title": t.title,
                "buyer_name": t.buyer.official_name if t.buyer else "Acheteur Inconnu",
                "main_category": t.main_category,
                "prestation_type": t.prestation_type,
                "status": t.status,
                "line_items": [
                    {"designation": i.designation, "technical_specs": i.technical_specs}
                    for i in t.line_items
                ],
            }
            diag = AIAvisDiagnostician.diagnose_tender(quick_dict)
            ai_rate = float(diag.matching_rate or 0.0)
            ai_domain = diag.primary_domain

        if ai_rate < min_ai_score:
            continue
        candidates.append((ai_rate, ai_domain, t))

    if sort_by == "ai_score_desc":
        candidates.sort(key=lambda x: (x[0], x[2].portal_id), reverse=True)

    queue = []
    for ai_rate, ai_domain, t in candidates[:limit]:
        if fetch_attachments and t.attachment_available:
            zip_path = Path("data/attachments") / f"tender_{t.portal_id}.zip"
            if not zip_path.exists():
                try:
                    from src.api.routes.feed import download_tender_attachment
                    await download_tender_attachment(portal_id=t.portal_id, session=session)
                except Exception as dl_err:
                    logger.debug(f"Pre-fetch attachment failed for #{t.portal_id}: {dl_err}")

        tender_dict = {
            "portal_id": t.portal_id,
            "reference": t.reference,
            "source_type": t.source_type,
            "title": t.title,
            "buyer_name": t.buyer.official_name if t.buyer else "Acheteur Inconnu",
            "execution_location": t.execution_location,
            "main_category": t.main_category,
            "prestation_type": t.prestation_type,
            "deadline_at": t.deadline_at.isoformat() if t.deadline_at else "",
            "ai_matching_rate": ai_rate,
            "ai_primary_domain": ai_domain,
            "line_items": [
                {
                    "item_order": i.item_order,
                    "designation": i.designation,
                    "technical_specs": i.technical_specs,
                    "quantity": float(i.quantity) if i.quantity is not None else 1.0,
                    "unit": i.unit or "U",
                }
                for i in t.line_items
            ],
        }
        cps = CPSDeterministicExtractor.extract(tender_dict)
        market_ctx = await fetch_market_context_for_tender(session, t)
        spent_ytd = market_ctx.get("buyer_spent_ytd_mad")
        if spent_ytd is not None:
            market_ctx["art91_headroom_mad"] = max(0.0, 500000.0 - spent_ytd)

        queue.append({
            **tender_dict,
            "cps_findings": cps.model_dump(),
            "market_context": market_ctx,
            "existing_study": (
                antigravity_study_manager.get_study(t.portal_id).model_dump()
                if t.portal_id in studied_ids else None
            ),
        })

    return {
        "success": True,
        "count": len(queue),
        "sort_by": sort_by,
        "already_studied_total": len(studied_ids),
        "queue": queue,
    }


@router.get("/antigravity/study/{portal_id}")
async def get_antigravity_study(
    portal_id: int,
    user: User = Depends(get_current_user),
):
    """Returns the saved Antigravity manual AI study for an avis, if any (authenticated)."""
    study = antigravity_study_manager.get_study(portal_id)
    if not study:
        raise HTTPException(status_code=404, detail=f"Aucune étude Antigravity enregistrée pour #{portal_id}.")
    return study.model_dump()


@router.post("/antigravity/study/{portal_id}")
async def save_antigravity_study(
    portal_id: int,
    payload: AntigravityStudyInput,
    user: User = Depends(require_role(["admin", "analyst"])),
):
    """Saves or updates a local Antigravity AI diagnosis for a specific avis."""
    record = AntigravityStudyRecord(
        portal_id=portal_id,
        verdict=payload.verdict,
        priority_tier=payload.priority_tier,
        opportunity_score=payload.opportunity_score,
        technical_fit_x=payload.technical_fit_x,
        commercial_value_y=payload.commercial_value_y,
        win_probability_z=payload.win_probability_z,
        why_reasons=payload.why_reasons,
        cps_findings=payload.cps_findings,
        bid_strategy=payload.bid_strategy,
        custom_prompt_used=payload.custom_prompt_used,
        studied_by=f"antigravity ({user.username or user.email})",
    )
    saved = antigravity_study_manager.save_study(record)
    invalidate_tender_cache(portal_id)
    from src.api.routes.feed import _FEED_SCORED_CACHE
    _FEED_SCORED_CACHE.clear()
    return {"success": True, "study": saved.model_dump()}


@router.post("/antigravity/batch-update")
async def batch_update_antigravity_studies(
    payload: AntigravityBatchInput,
    user: User = Depends(require_role(["admin", "analyst"])),
):
    """Bulk-saves multiple local Antigravity AI studies and invalidates feed cache."""
    count = antigravity_study_manager.save_batch(payload.studies)
    for rec in payload.studies:
        invalidate_tender_cache(rec.portal_id)
    from src.api.routes.feed import _FEED_SCORED_CACHE
    _FEED_SCORED_CACHE.clear()
    return {"success": True, "updated_count": count}
