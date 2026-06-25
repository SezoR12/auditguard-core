import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Numeric, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from decimal import Decimal

from app.database import Base
from app.models.enums import FileType, DocCategory, DocStatus


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[FileType] = mapped_column(SAEnum(FileType, name="file_type"), nullable=False)
    doc_category: Mapped[DocCategory] = mapped_column(SAEnum(DocCategory, name="doc_category"), nullable=False)
    status: Mapped[DocStatus] = mapped_column(SAEnum(DocStatus, name="doc_status"), default=DocStatus.pending, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True)
    ocr_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    extracted_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
