from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Float, BigInteger, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base

class IngestionBatch(Base):
    """
    Persistent ledger record for each ingestion batch run.
    Ensures complete traceability of crawl sessions, ingested volume, quality, and errors.
    """
    __tablename__ = "ingestion_batches"

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False) # 'scheduled', 'manual', 'diagnostic_remediation'
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True) # 'completed', 'in_progress', 'missed', 'failed', 'pending'
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pages_requested: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    pages_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cards_scraped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tenders_ingested: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    line_items_extracted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alerts_dispatched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, default=95.0, nullable=False)
    errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), default="Système (Daemon)", nullable=False)
    first_bdc_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    last_bdc_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    current_step: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_phase: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    progress_pct: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
