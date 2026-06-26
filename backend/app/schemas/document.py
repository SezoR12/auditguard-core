"""Schemas for the document ingestion pipeline."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import DocCategory, DocStatus, FileType

# The Phase-2 UI exposes richer category labels than the existing `doc_category`
# enum. We map incoming category keys to the stored enum so we don't have to
# ALTER the live enum type. The original requested key is preserved in
# Document.extracted_data["category_key"] for later phases.
CATEGORY_KEY_TO_ENUM: dict[str, DocCategory] = {
    "invoice": DocCategory.invoice,
    "receipt": DocCategory.receipt,
    "contract": DocCategory.contract,
    "bank_statement": DocCategory.statement,
    "statement": DocCategory.statement,
    "inventory_report": DocCategory.report,
    "report": DocCategory.report,
    "encrypted_accounting": DocCategory.report,
    "other": DocCategory.other,
}

ALLOWED_CATEGORY_KEYS = set(CATEGORY_KEY_TO_ENUM.keys())


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    file_type: FileType
    doc_category: DocCategory
    status: DocStatus
    uploaded_by: uuid.UUID
    company_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    ocr_status: str | None = None
    confidence_score: Decimal | None = None
    created_at: datetime


class UploadResponse(BaseModel):
    document_id: uuid.UUID
    status: DocStatus
    file_type: FileType
    doc_category: DocCategory
    original_filename: str
    message: str = "تم الرفع بنجاح"
