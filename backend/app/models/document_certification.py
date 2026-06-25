import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class DocumentCertification(Base):
    __tablename__ = "document_certifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    auditor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    certified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    corrections_made: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
