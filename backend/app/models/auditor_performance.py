"""Per-auditor, per-day performance aggregation (tasks + demerits)."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class AuditorPerformance(Base):
    __tablename__ = "auditor_performance"
    __table_args__ = (
        UniqueConstraint("auditor_id", "perf_date", name="uq_auditor_perf_day"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    auditor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    perf_date: Mapped[date] = mapped_column(Date, nullable=False)

    total_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tasks_completed_on_time: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tasks_delayed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    demerit_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    efficiency_score: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("0.00"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
