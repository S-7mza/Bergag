from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

@dataclass
class AwardsSyncRecord:
    batch_id: str
    status: str       # "in_progress", "completed", "completed_with_errors", "failed", "aborted"
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    pages_requested: int = 5
    pages_completed: int = 0
    awards_ingested: int = 0
    errors_count: int = 0
    error_details: Optional[str] = None
    triggered_by: str = "Opérateur"
    portal_total_archive: int = 0
    current_step: str = "En attente"
    progress_pct: int = 0
    recent_awards: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "status": self.status,
            "domain": "awards",
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": round(self.duration_seconds, 1),
            "pages_requested": self.pages_requested,
            "pages_completed": self.pages_completed,
            "awards_ingested": self.awards_ingested,
            "errors_count": self.errors_count,
            "error_details": self.error_details,
            "triggered_by": self.triggered_by,
            "portal_total_archive": self.portal_total_archive,
            "current_step": self.current_step,
            "progress_pct": self.progress_pct,
            "recent_awards": self.recent_awards[:15]
        }
