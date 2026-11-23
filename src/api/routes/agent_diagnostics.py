import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db_session
from src.engine.ai_matching_agent import ai_matching_agent
from src.engine.ai_diagnostician import AIMatchingDiagnosis
from src.api.schemas import DiagnoseBatchRequest, DiagnoseBatchResponse

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
    session: AsyncSession = Depends(get_db_session)
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
    session: AsyncSession = Depends(get_db_session)
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
