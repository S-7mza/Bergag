import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Body
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db_session
from src.models.user import User
from src.api.routes.auth import require_role
from src.ingestion.offline.importer import OfflineImporter, OfflineImportError

logger = logging.getLogger(__name__)

try:
    import python_multipart
    HAS_MULTIPART = True
except ImportError:
    try:
        import multipart
        HAS_MULTIPART = True
    except ImportError:
        HAS_MULTIPART = False

router = APIRouter(prefix="/api/admin/ingestion/offline", tags=["Offline Ingestion & Sync"])

if HAS_MULTIPART:
    @router.post("/upload")
    async def upload_offline_bundle(
        file: UploadFile = File(...),
        session: AsyncSession = Depends(get_db_session),
        user: User = Depends(require_role(["admin"]))
    ):
        """
        Universal offline bundle upload endpoint.
        Accepts portable offline export JSON bundles for both BDC consultations and Awards,
        validates the manifest and integrity checksum, and idempotently imports records into PostgreSQL.
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
else:
    @router.post("/upload")
    async def upload_offline_bundle_fallback():
        raise HTTPException(
            status_code=503,
            detail="Le support de téléversement multipart nécessite 'python-multipart'. Installez-le avec 'pip install python-multipart' ou utilisez l'endpoint JSON '/offline/sync-json'."
        )

@router.post("/sync-json")
async def sync_offline_bundle_json(
    bundle: Dict[str, Any] = Body(..., description="Bundle JSON contenant le manifeste et les items"),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_role(["admin"]))
):
    """
    Directly synchronizes an offline export JSON payload into PostgreSQL.
    Supports both BDC and Awards bundles. Useful for automated CI/CD pipelines, curl scripts, and local desktop sync.
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

@router.get("/list")
async def list_offline_exports(
    user: User = Depends(require_role(["admin", "analyst", "viewer"]))
):
    """
    Lists generated offline JSON bundles available in data/offline_exports/.
    """
    exp_dir = Path("data/offline_exports")
    if not exp_dir.exists():
        return []
    files = []
    for f in sorted(exp_dir.glob("*.json"), key=os.path.getmtime, reverse=True):
        if f.name.startswith("."):
            continue
        files.append({
            "filename": f.name,
            "path": str(f),
            "size_kb": round(f.stat().st_size / 1024, 1),
            "modified_at": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        })
    return files

@router.get("/download/{filename}")
async def download_offline_export(
    filename: str,
    user: User = Depends(require_role(["admin", "analyst", "viewer"]))
):
    """
    Downloads an offline export bundle JSON file.
    """
    file_path = Path("data/offline_exports") / filename
    if not file_path.exists() or not filename.endswith(".json") or filename.startswith("."):
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/json"
    )
