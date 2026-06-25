import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, ForeignKey, Numeric, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base
from app.models.enums import WasteCategory


class WasteMapItem(Base):
    __tablename__ = "waste_map_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    category: Mapped[WasteCategory] = mapped_column(SAEnum(WasteCategory, name="waste_category"), nullable=False)
    amount_iqd: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    department: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
