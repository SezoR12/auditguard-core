import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base
from app.models.enums import OutputType


class AnalyticsOutput(Base):
    __tablename__ = "analytics_outputs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    output_type: Mapped[OutputType] = mapped_column(SAEnum(OutputType, name="output_type"), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    trust_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
