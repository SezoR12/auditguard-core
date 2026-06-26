"""In-app notifications for owners/management (auditor-restricted via RLS)."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    # Recipient. NULL = broadcast to all owners/management of the company.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    category: Mapped[str] = mapped_column(String(40), nullable=False)  # risk_alert/task_overdue/digest
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    financial_impact: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    # Drill-down target, e.g. {"layer": "analytics", "document_id": "..."}.
    link: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ref_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    whatsapp_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
