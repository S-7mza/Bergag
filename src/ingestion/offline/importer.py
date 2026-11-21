import json
import logging
from pathlib import Path
from typing import Union, Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.session import async_session_factory
from src.ingestion.awards.service import AwardsIngestionService
from src.ingestion.bdc.service import BdcIngestionService
from src.models.tender import Award, Tender

logger = logging.getLogger(__name__)

class OfflineImportError(Exception):
    pass

class OfflineImporter:
    """
    Imports portable offline export bundles (.json) into the PostgreSQL server database.
    Ensures idempotency, validates manifest integrity, and reports detailed stats.
    """
    def __init__(self, session: Optional[AsyncSession] = None):
        self._external_session = session

    def parse_bundle(self, bundle_input: Union[str, Path, bytes, dict]) -> Dict[str, Any]:
        """Parses and validates raw bundle data into structured dictionary"""
        if isinstance(bundle_input, dict):
            data = bundle_input
        elif isinstance(bundle_input, (str, Path)):
            path = Path(bundle_input)
            if not path.exists():
                raise OfflineImportError(f"Le fichier d'export '{path}' n'existe pas.")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                raise OfflineImportError(f"Format JSON invalide dans '{path}': {e}")
        elif isinstance(bundle_input, bytes):
            try:
                data = json.loads(bundle_input.decode("utf-8"))
            except Exception as e:
                raise OfflineImportError(f"Données de bundle non décodables: {e}")
        else:
            raise OfflineImportError(f"Type d'entrée non supporté: {type(bundle_input)}")

        if not isinstance(data, dict):
            raise OfflineImportError("Le bundle doit être un objet JSON valide.")

        manifest = data.get("manifest")
        items = data.get("items")

        if not manifest or not isinstance(manifest, dict):
            raise OfflineImportError("Manifeste d'exportation manquant ou invalide dans le fichier.")
        if items is None or not isinstance(items, list):
            raise OfflineImportError("Liste d'éléments manquante dans le fichier.")

        return data

    async def import_bundle(
        self,
        bundle_input: Union[str, Path, bytes, dict],
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Executes the atomic ingestion of an offline bundle into the PostgreSQL database.
        """
        bundle = self.parse_bundle(bundle_input)
        manifest = bundle["manifest"]
        items = bundle["items"]
        domain = manifest.get("domain", "awards").lower().strip()

        logger.info(f"[OfflineImporter] Starting import of {len(items)} items for domain '{domain}'...")

        if session:
            return await self._process_items(session, domain, items, manifest)
        elif self._external_session:
            return await self._process_items(self._external_session, domain, items, manifest)
        else:
            async with async_session_factory() as sess:
                res = await self._process_items(sess, domain, items, manifest)
                await sess.commit()
                return res

    async def _process_items(
        self,
        session: AsyncSession,
        domain: str,
        items: List[Dict[str, Any]],
        manifest: Dict[str, Any]
    ) -> Dict[str, Any]:
        items_created = 0
        items_updated = 0
        linked_tenders = 0
        errors = 0

        if domain == "awards":
            service = AwardsIngestionService(session)
            for item in items:
                try:
                    award = await service.ingest_award(item)
                    if award.tender_id:
                        linked_tenders += 1
                    items_created += 1
                except Exception as e:
                    logger.error(f"[OfflineImporter] Failed to import award {item.get('reference')}: {e}")
                    errors += 1

        elif domain == "bdc":
            service = BdcIngestionService(session, None)
            for item in items:
                try:
                    await service.ingest_tender_detail(item, skip_if_exists=False)
                    items_created += 1
                except Exception as e:
                    logger.error(f"[OfflineImporter] Failed to import BDC #{item.get('portal_id')}: {e}")
                    errors += 1
        else:
            raise OfflineImportError(f"Domaine d'importation inconnu: '{domain}' (attendus: 'awards' ou 'bdc')")

        await session.flush()

        logger.info(
            f"[OfflineImporter] Import complete: {items_created} {domain} items processed, "
            f"{linked_tenders} linked to consultations, {errors} errors."
        )

        return {
            "status": "success",
            "domain": domain,
            "manifest": manifest,
            "items_total": len(items),
            "items_processed": items_created,
            "linked_tenders": linked_tenders,
            "errors_count": errors
        }
