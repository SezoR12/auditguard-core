"""Schemas for the OCR certification workflow."""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel


class CertificationDocOut(BaseModel):
    """The next document awaiting human certification."""

    document_id: uuid.UUID
    original_filename: str
    file_type: str
    doc_category: str
    confidence_score: float | None = None
    # Data URL (base64) of the decrypted original image for display.
    original_image_url: str | None = None
    # {fields, confidences, color_flags, overall_confidence, raw_text}
    extracted_data: dict[str, Any] | None = None


class CertifyRequest(BaseModel):
    corrected_fields: dict[str, Any] | None = None
    is_valid: bool = True


class CertifyResponse(BaseModel):
    document_id: uuid.UUID
    certification_id: uuid.UUID
    status: str
    ledger_hash: str
    message: str = "تم اعتماد المستند بنجاح"
