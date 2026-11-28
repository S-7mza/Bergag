import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

ANTIGRAVITY_LEDGER_PATH = Path("data/antigravity_studies_ledger.json")


class AntigravityStudyRecord(BaseModel):
    """
    Manual/Local AI Study & Decision record produced via Antigravity
    for a specific procurement avis, at zero external LLM API cost.
    """
    portal_id: int
    verdict: str = Field(..., pattern="^(GO|CONSIDER|NO-GO)$")
    priority_tier: str = Field(default="P2", pattern="^(P1|P2|P3|ARCHIVE)$")
    opportunity_score: float = Field(..., ge=0.0, le=100.0)
    technical_fit_x: float = Field(default=0.0, ge=0.0, le=100.0)
    commercial_value_y: float = Field(default=0.0, ge=0.0, le=100.0)
    win_probability_z: float = Field(default=0.0, ge=0.0, le=100.0)
    why_reasons: List[str] = Field(default_factory=list, description="Explicit X, Y, Z reasons why this offer deserves attention or not")
    cps_findings: Dict[str, Any] = Field(default_factory=dict)
    bid_strategy: str = Field(default="")
    custom_prompt_used: Optional[str] = None
    studied_by: str = Field(default="antigravity")
    studied_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AntigravityStudyManager:
    """
    Manages zero-cost local AI studies executed via Antigravity.
    Persists atomically to data/antigravity_studies_ledger.json.
    """

    def __init__(self, ledger_path: Optional[Path] = None):
        self.ledger_path = ledger_path or ANTIGRAVITY_LEDGER_PATH
        self._studies: Dict[int, AntigravityStudyRecord] = {}
        self._load()

    def _load(self):
        if self.ledger_path.exists():
            try:
                raw = json.loads(self.ledger_path.read_text(encoding="utf-8"))
                self._studies = {
                    int(k): AntigravityStudyRecord(**v)
                    for k, v in raw.items()
                }
            except Exception as e:
                logger.warning(f"Could not load Antigravity studies ledger: {e}")
                self._studies = {}

    def _persist(self):
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.ledger_path.with_suffix(".tmp")
            payload = {str(k): v.model_dump() for k, v in self._studies.items()}
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.ledger_path)
        except Exception as e:
            logger.error(f"Failed to persist Antigravity studies ledger: {e}")

    def get_study(self, portal_id: int) -> Optional[AntigravityStudyRecord]:
        return self._studies.get(int(portal_id))

    def list_studied_ids(self) -> set[int]:
        return set(self._studies.keys())

    def save_study(self, record: AntigravityStudyRecord) -> AntigravityStudyRecord:
        record.studied_at = datetime.now(timezone.utc).isoformat()
        self._studies[int(record.portal_id)] = record
        self._persist()
        return record

    def save_batch(self, records: List[AntigravityStudyRecord]) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        for rec in records:
            rec.studied_at = now_iso
            self._studies[int(rec.portal_id)] = rec
        self._persist()
        return len(records)

    def delete_study(self, portal_id: int) -> bool:
        pid = int(portal_id)
        if pid in self._studies:
            del self._studies[pid]
            self._persist()
            return True
        return False


antigravity_study_manager = AntigravityStudyManager()
