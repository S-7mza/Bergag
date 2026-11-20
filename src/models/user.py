import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin

# Default Permissions Matrix by Role
ROLE_PERMISSIONS = {
    "admin": [
        "feed:view", "feed:export", "tender:action", "tender:pricing_calculator",
        "radar:view_all", "radar:article91_alarms", "profiles:manage",
        "crawler:trigger", "crawler:telemetry", "users:manage",
        "batches:manage", "quality:view", "diagnostic:run"
    ],
    "analyst": [
        "feed:view", "feed:export", "tender:action", "tender:pricing_calculator",
        "radar:view_competitors", "profiles:view", "crawler:telemetry"
    ],
    "viewer": [
        "feed:view_curated", "tender:view_summary"
    ]
}

class User(Base, TimestampMixin):
    """Normalized enterprise user account with RBAC"""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="viewer", nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(128), default="Collaborateur", nullable=False)
    avatar_color: Mapped[str] = mapped_column(String(32), default="emerald", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def permissions(self) -> List[str]:
        return ROLE_PERMISSIONS.get(self.role, ROLE_PERMISSIONS["viewer"])
