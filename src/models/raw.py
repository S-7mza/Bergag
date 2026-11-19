import uuid
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base

class RawIngestionLog(Base):
    """
    Immutable raw snapshot layer. Stores raw HTTP payloads with SHA-256 hash
    before parsing, ensuring zero data loss and 100% historical re-parseability.
    """
    __tablename__ = "raw_ingestion_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    portal_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    page_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 'listing', 'detail', 'result'
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    html_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True) # SHA-256
    scraper_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0.0")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )

