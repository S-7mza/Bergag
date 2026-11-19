import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin

class CompanyProfile(Base, TimestampMixin):
    """Declarative company profile entity"""
    __tablename__ = "company_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    profile_name: Mapped[str] = mapped_column(String(128), nullable=False)
    config_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class ProfileMatch(Base):
    """Scoring results of a tender against a company profile"""
    __tablename__ = "profile_matches"
    __table_args__ = (
        UniqueConstraint("profile_id", "tender_id", name="uq_profile_tender_match"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("company_profiles.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    tender_id: Mapped[int] = mapped_column(
        BigInteger, 
        ForeignKey("tenders.portal_id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    overall_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    coverage_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    semantic_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    feasibility_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    commercial_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    decision_recommendation: Mapped[str] = mapped_column(String(16), nullable=False) # 'GO', 'CONSIDER', 'NO-GO'
    line_item_matches: Mapped[Any] = mapped_column(JSONB, nullable=False)
    red_flags: Mapped[Any] = mapped_column(JSONB, default=list, nullable=False)
    llm_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )

class UserTenderAction(Base):
    """Founder interactive action tracking (shortlist, skip, bidded, etc.)"""
    __tablename__ = "user_tender_actions"
    __table_args__ = (
        UniqueConstraint("profile_id", "tender_id", "action", name="uq_user_action"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("company_profiles.id", ondelete="CASCADE"), 
        nullable=False
    )
    tender_id: Mapped[int] = mapped_column(
        BigInteger, 
        ForeignKey("tenders.portal_id", ondelete="CASCADE"), 
        nullable=False
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False) # 'viewed', 'shortlisted', 'bidded', 'won', 'lost', 'rejected'
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actioned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )

