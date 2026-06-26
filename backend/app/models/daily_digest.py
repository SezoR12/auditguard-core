"""Daily digest records (one per owner per day)."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class DailyDigest(Base):
    __tablename__ = "daily_digests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    digest_date: Mapped[date] = mapped_column(Date, nullable=False)
    waste_total_iqd: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tasks_overdue: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alerts_open: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trust_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    whatsapp_sent: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
