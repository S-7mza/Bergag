from enum import Enum
from typing import Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timezone

class IngestionDomain(str, Enum):
    BDC = "bdc"
    AWARDS = "awards"

class IngestionJobStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"

@dataclass
class IngestionProgressEvent:
    domain: IngestionDomain
    phase: str
    step_description: str
    items_processed: int = 0
    items_total: int = 0
    current_item: Optional[Dict[str, Any]] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

# Type alias for async event callbacks
ProgressCallback = Callable[[str, Dict[str, Any]], Awaitable[None]]
AbortCheckCallback = Callable[[], bool]
