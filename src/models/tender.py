import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Integer, 
    Numeric, String, Text, func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, TimestampMixin

class Buyer(Base, TimestampMixin):
    """Normalized public buyer (commune, ministère, etc.)"""
    __tablename__ = "buyers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    official_name: Mapped[str] = mapped_column(Text, nullable=False)
    buyer_type: Mapped[str] = mapped_column(String(64), nullable=False, default="commune")
    region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    tenders: Mapped[List["Tender"]] = relationship("Tender", back_populates="buyer")

class Tender(Base, TimestampMixin):
    """Canonical public procurement consultation (BDC or Marché Public)"""
    __tablename__ = "tenders"

    portal_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), default="bdc", nullable=False)
    reference: Mapped[str] = mapped_column(String(64), nullable=False)
    compound_natural_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True) # buyer_slug:ref:year
    
    buyer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("buyers.id", ondelete="RESTRICT"), 
        nullable=False
    )
    
    title: Mapped[str] = mapped_column(Text, nullable=False)
    main_category: Mapped[str] = mapped_column(String(32), nullable=False, default="Fournitures")
    prestation_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    normalized_city: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    normalized_region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    
    attachment_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attachment_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    buyer: Mapped["Buyer"] = relationship("Buyer", back_populates="tenders")
    line_items: Mapped[List["LineItem"]] = relationship(
        "LineItem", 
        back_populates="tender", 
        cascade="all, delete-orphan",
        order_by="LineItem.item_order"
    )
    award: Mapped[Optional["Award"]] = relationship("Award", back_populates="tender", uselist=False)

class LineItem(Base):
    """Individual line item from tender bill of quantities (Bordereau / Accordion)"""
    __tablename__ = "line_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    tender_id: Mapped[int] = mapped_column(
        BigInteger, 
        ForeignKey("tenders.portal_id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    item_order: Mapped[int] = mapped_column(Integer, nullable=False)
    designation: Mapped[str] = mapped_column(Text, nullable=False)
    technical_specs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(32), default="U", nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tva_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("20.00"), nullable=True)
    warranty_required: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_brand: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )

    tender: Mapped["Tender"] = relationship("Tender", back_populates="line_items")

class Award(Base):
    """Award notice from historical results archive (/bdc/entreprise/consultation/resultat)"""
    __tablename__ = "awards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    tender_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, 
        ForeignKey("tenders.portal_id", ondelete="SET NULL"), 
        nullable=True,
        index=True
    )
    compound_ref_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reference: Mapped[str] = mapped_column(String(64), nullable=False)
    buyer_name_raw: Mapped[str] = mapped_column(Text, nullable=False)
    title_raw: Mapped[str] = mapped_column(Text, nullable=False)
    winner_name: Mapped[str] = mapped_column(Text, nullable=False)
    winner_identifier: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    amount_ttc: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    devis_received_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False) # 'Attribué', 'Infructueux'
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )

    tender: Mapped[Optional["Tender"]] = relationship("Tender", back_populates="award")

