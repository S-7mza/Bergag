import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from src.ingestion.batches.models import AwardsSyncRecord
from src.ingestion.awards.pipeline import AwardsIngestionPipeline, AWARDS_LEDGER_FILE

logger = logging.getLogger(__name__)

class AwardsBatchManager:
    """
    Dedicated manager for orchestrating and monitoring Awards / Results Ingestion jobs.
    Maintains clean domain separation from active BDC batch tracking.
    """
    def __init__(self):
        self.active_job: Optional[AwardsSyncRecord] = None
        self._abort_requested: bool = False
        self.history: List[AwardsSyncRecord] = self._load_initial_history()

    def _load_initial_history(self) -> List[AwardsSyncRecord]:
        records: List[AwardsSyncRecord] = []
        if AWARDS_LEDGER_FILE.exists():
            try:
                with open(AWARDS_LEDGER_FILE, "r", encoding="utf-8") as f:
                    raw_list = json.load(f)
                    for item in raw_list:
                        started = datetime.fromisoformat(item["started_at"]) if item.get("started_at") else datetime.now(timezone.utc)
                        completed = datetime.fromisoformat(item["completed_at"]) if item.get("completed_at") else None
                        records.append(AwardsSyncRecord(
                            batch_id=item["batch_id"],
                            status=item.get("status", "completed"),
                            started_at=started,
                            completed_at=completed,
                            duration_seconds=float(item.get("duration_seconds", 0.0)),
                            pages_requested=int(item.get("pages_requested", 5)),
                            pages_completed=int(item.get("pages_completed", 0)),
                            awards_ingested=int(item.get("awards_ingested", 0)),
                            errors_count=int(item.get("errors_count", 0)),
                            error_details=item.get("error_details"),
                            triggered_by=item.get("triggered_by", "Opérateur"),
                            portal_total_archive=int(item.get("portal_total_archive", 0)),
                            current_step="Terminé",
                            progress_pct=100,
                            recent_awards=item.get("recent_awards", [])
                        ))
            except Exception as e:
                logger.warning(f"Could not load awards ledger history: {e}")
        return records

    def is_sync_running(self) -> bool:
        return self.active_job is not None and self.active_job.status == "in_progress"

    async def execute_sync(
        self,
        pages: int = 5,
        page_size: int = 50,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        user_name: str = "Opérateur"
    ) -> Dict[str, Any]:
        if self.is_sync_running():
            raise RuntimeError("Une synchronisation des attributions est déjà en cours d'exécution.")

        batch_id = f"AW-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        self._abort_requested = False
        record = AwardsSyncRecord(
            batch_id=batch_id,
            status="in_progress",
            started_at=datetime.now(timezone.utc),
            pages_requested=pages,
            triggered_by=user_name,
            current_step="Initialisation du scan...",
            progress_pct=5
        )
        self.active_job = record

        async def on_progress(event_type: str, data: Dict[str, Any]):
            if not self.active_job:
                return
            desc = data.get("step_description")
            if desc:
                self.active_job.current_step = desc
            
            phase = data.get("phase")
            if phase == "plan":
                self.active_job.progress_pct = 10
            elif phase == "discovery":
                page = data.get("page", 1)
                max_p = data.get("max_pages", pages)
                self.active_job.pages_completed = page
                self.active_job.progress_pct = min(90, int(15 + (page / max_p) * 75))
                if data.get("portal_total"):
                    self.active_job.portal_total_archive = data["portal_total"]
            elif phase == "award_item":
                self.active_job.awards_ingested = data.get("processed_count", self.active_job.awards_ingested + 1)
                if data.get("award"):
                    self.active_job.recent_awards.insert(0, data["award"])
                    self.active_job.recent_awards = self.active_job.recent_awards[:15]
            elif phase == "completed":
                self.active_job.progress_pct = 100

        def is_aborted() -> bool:
            return self._abort_requested

        pipeline = AwardsIngestionPipeline()
        try:
            summary = await pipeline.run(
                max_pages=pages,
                page_size=page_size,
                date_start=date_start,
                date_end=date_end,
                keyword=keyword,
                category=category,
                progress_callback=on_progress,
                is_aborted_callback=is_aborted,
                batch_id=batch_id,
                triggered_by=user_name
            )
            record.status = summary.get("status", "completed")
            record.completed_at = datetime.now(timezone.utc)
            record.duration_seconds = summary.get("duration_seconds", 0.0)
            record.awards_ingested = summary.get("awards_ingested", 0)
            record.errors_count = summary.get("errors_count", 0)
            record.portal_total_archive = summary.get("portal_total_archive", 0)
            record.current_step = f"Terminé : {record.awards_ingested} attributions ingérées"
            record.progress_pct = 100
            self.history.insert(0, record)
            return record.to_dict()
        except Exception as e:
            logger.error(f"Awards sync execution error: {e}", exc_info=True)
            record.status = "failed"
            record.error_details = str(e)
            record.completed_at = datetime.now(timezone.utc)
            record.current_step = f"Échec : {e}"
            self.history.insert(0, record)
            return record.to_dict()
        finally:
            self.active_job = None

    def abort_sync(self, user_name: str = "Opérateur") -> Dict[str, Any]:
        if not self.is_sync_running():
            return {"status": "noop", "message": "Aucune synchronisation d'attributions active à interrompre."}

        self._abort_requested = True
        if self.active_job:
            self.active_job.status = "aborted"
            self.active_job.current_step = f"Interrompu par {user_name}"
        return {"status": "aborted", "message": f"Demande d'interruption transmise par {user_name}."}

    def get_dashboard_state(self) -> Dict[str, Any]:
        return {
            "is_running": self.is_sync_running(),
            "active_job": self.active_job.to_dict() if self.active_job else None,
            "history": [r.to_dict() for r in self.history[:20]]
        }

# Global singleton for awards ingestion management
awards_batch_manager = AwardsBatchManager()
