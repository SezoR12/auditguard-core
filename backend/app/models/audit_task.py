import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Integer, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base
from app.models.enums import TaskType, TaskStatus


class AuditTask(Base):
    __tablename__ = "audit_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    auditor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    task_type: Mapped[TaskType] = mapped_column(SAEnum(TaskType, name="task_type"), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus, name="task_status"), default=TaskStatus.pending, nullable=False)
    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    demerit_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
