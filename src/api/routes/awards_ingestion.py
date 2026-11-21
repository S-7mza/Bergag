import logging
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, File, UploadFile, Body
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.session import get_db_session
from src.models.user import User
from src.api.routes.auth import require_role
from src.ingestion.awards.auditor import AwardsAuditor
from src.ingestion.batches.manager import awards_batch_manager
from src.ingestion.offline.importer import OfflineImporter, OfflineImportError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/ingestion/awards", tags=["Awards Ingestion & Archive Sync"])

class AwardsSyncRequest(BaseModel):
    pages: int = Field(default=5, ge=1, le=50, description="Nombre de pages de résultats à scanner (50 attributions / page)")
    page_size: int = Field(default=50, ge=10, le=50, description="Taille de page TGR (recommandé 50)")
    date_start: Optional[str] = Field(default=None, description="Date début publication résultat (JJ/MM/AAAA)")
    date_end: Optional[str] = Field(default=None, description="Date fin publication résultat (JJ/MM/AAAA)")
    keyword: Optional[str] = Field(default=None, description="Mot-clé de filtrage")
    category: Optional[str] = Field(default=None, description="Catégorie (1: Travaux, 2: Fournitures, 3: Services)")

@router.get("/stats")
async def get_awards_stats(
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_role(["admin", "analyst", "viewer"]))
):
    """
    Returns real-time database metrics for the Awards table:
    Total awards, total awarded volume (MAD TTC), average density,
    tender cross-linking rate, and fallback status.
    """
    auditor = AwardsAuditor(session)
    return await auditor.get_stats()

@router.get("/state")
async def get_awards_sync_state(
    user: User = Depends(require_role(["admin", "analyst", "viewer"]))
):
    """
    Returns the live orchestration state of the Awards Ingestion Pipeline:
    Whether a crawl is running, current step progress, and recent batch history.
    """
    return awards_batch_manager.get_dashboard_state()

@router.post("/sync")
async def trigger_awards_sync(
    req: AwardsSyncRequest,
    bg_tasks: BackgroundTasks,
    user: User = Depends(require_role(["admin"]))
):
    """
    Triggers an autonomous awards synchronization cycle in the background (Admin only).
    Crawls historical results from /bdc/entreprise/consultation/resultat at pageSize=50.
    """
    if awards_batch_manager.is_sync_running():
        raise HTTPException(
            status_code=409,
            detail="Une synchronisation des attributions est déjà en cours. Veuillez patienter ou l'interrompre."
        )

    bg_tasks.add_task(
        awards_batch_manager.execute_sync,
        pages=req.pages,
        page_size=req.page_size,
        date_start=req.date_start,
        date_end=req.date_end,
        keyword=req.keyword,
        category=req.category,
        user_name=user.full_name
    )

    return {
        "status": "sync_started",
        "message": f"Synchronisation des attributions démarrée ({req.pages} pages, ~{req.pages * req.page_size} avis).",
        "pages_requested": req.pages
    }

@router.post("/abort")
async def abort_awards_sync(
    user: User = Depends(require_role(["admin"]))
):
    """
    Aborts the currently running awards synchronization job (Admin only).
    """
    return awards_batch_manager.abort_sync(user_name=user.full_name)

@router.post("/offline/upload")
async def upload_offline_bundle(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_role(["admin"]))
):
    """
    Uploads and synchronizes a portable offline export package (.json)
    generated from a local collector machine into the PostgreSQL database.
    Supports both Awards and BDC notice bundles with idempotent upsert.
    """
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Format de fichier non supporté. Veuillez uploader un bundle JSON (.json).")

    try:
        content = await file.read()
        importer = OfflineImporter()
        res = await importer.import_bundle(content, session=session)
        await session.commit()
        return {
            "status": "success",
            "filename": file.filename,
            "domain": res["domain"],
            "items_total": res["items_total"],
            "items_processed": res["items_processed"],
            "linked_tenders": res["linked_tenders"],
            "errors_count": res["errors_count"],
            "message": f"{res['items_processed']} éléments ({res['domain']}) synchronisés avec succès depuis '{file.filename}'."
        }
    except OfflineImportError as oie:
        raise HTTPException(status_code=422, detail=f"Erreur de validation du bundle: {oie}")
    except Exception as e:
        logger.error(f"Failed to process offline bundle upload '{file.filename}': {e}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'importation: {e}")

@router.post("/offline/sync-json")
async def sync_offline_bundle_json(
    bundle: Dict[str, Any] = Body(..., description="Bundle JSON contenant le manifeste et les items"),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_role(["admin"]))
):
    """
    Directly synchronizes an offline export JSON payload into PostgreSQL.
    Useful for automated CI/CD pipelines, curl scripts, and local desktop sync.
    """
    try:
        importer = OfflineImporter()
        res = await importer.import_bundle(bundle, session=session)
        await session.commit()
        return {
            "status": "success",
            "domain": res["domain"],
            "items_total": res["items_total"],
            "items_processed": res["items_processed"],
            "linked_tenders": res["linked_tenders"],
            "errors_count": res["errors_count"],
            "message": f"{res['items_processed']} éléments ({res['domain']}) synchronisés avec succès."
        }
    except OfflineImportError as oie:
        raise HTTPException(status_code=422, detail=f"Erreur de validation du bundle: {oie}")
    except Exception as e:
        logger.error(f"Failed to sync offline bundle JSON: {e}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'importation: {e}")

@router.post("/offline/export")
async def trigger_offline_export(
    pages: int = 5,
    keyword: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    domain: str = "awards",
    user: User = Depends(require_role(["admin", "analyst"]))
):
    """
    Crawls data locally without database connection and saves portable JSON bundle.
    Domain can be 'awards' or 'bdc'.
    """
    from src.ingestion.offline.exporter import OfflineExporter
    exporter = OfflineExporter()
    if domain == "awards":
        res = await exporter.collect_awards(
            max_pages=pages,
            page_size=50,
            keyword=keyword,
            date_start=date_start,
            date_end=date_end
        )
    elif domain == "bdc":
        res = await exporter.collect_bdc(max_pages=pages, page_size=50)
    else:
        raise HTTPException(status_code=400, detail="Domaine invalide (choisir 'awards' ou 'bdc')")

    return res

@router.get("/offline/list")
async def list_offline_exports(
    user: User = Depends(require_role(["admin", "analyst", "viewer"]))
):
    """
    Lists generated offline JSON bundles available in data/offline_exports/.
    """
    from pathlib import Path
    import os
    exp_dir = Path("data/offline_exports")
    if not exp_dir.exists():
        return []
    files = []
    for f in sorted(exp_dir.glob("*.json"), key=os.path.getmtime, reverse=True):
        files.append({
            "filename": f.name,
            "path": str(f),
            "size_kb": round(f.stat().st_size / 1024, 1),
            "modified_at": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        })
    return files

@router.get("/offline/download/{filename}")
async def download_offline_export(
    filename: str,
    user: User = Depends(require_role(["admin", "analyst", "viewer"]))
):
    """
    Downloads an offline export bundle JSON file.
    """
    from fastapi.responses import FileResponse
    from pathlib import Path
    file_path = Path("data/offline_exports") / filename
    if not file_path.exists() or not filename.endswith(".json"):
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/json"
    )



