"""Certification API — the auditor's human-in-the-loop review workflow.

GET  /certification/next          -> oldest doc in 'ocr_processing' for the
                                     auditor's company, with decrypted image
                                     (base64) + extracted fields & color flags.
POST /certification/{doc_id}/certify -> save corrections, mark certified,
                                     write a hash-chained ledger entry, and
                                     enqueue (placeholder) AI analysis.
"""
from __future__ import annotations

import base64
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.database import get_session
from app.models import Document, DocumentCertification, User
from app.models.enums import DocStatus, FileType
from app.services.audit_log import (
    DOCUMENT_FIELDS,
    correction_reason,
    log_certification_insert,
    log_document_update,
    model_snapshot,
)
from app.schemas.certification import (
    CertificationDocOut,
    CertifyRequest,
    CertifyResponse,
)
from app.storage import load_decrypted

router = APIRouter(prefix="/certification", tags=["certification"])

MSG_NONE_PENDING = "لا توجد مستندات بانتظار الاعتماد"
MSG_NOT_FOUND = "المستند غير موجود"
MSG_NOT_READY = "المستند ليس جاهزاً للاعتماد"
MSG_FORBIDDEN_COMPANY = "لا يمكنك اعتماد مستند خارج نطاق شركتك"

_MIME_BY_FILETYPE = {
    FileType.image: "image/png",  # display hint; browsers sniff anyway
    FileType.pdf: "application/pdf",
}


def _data_url(file_type: FileType, raw: bytes) -> str:
    mime = _MIME_BY_FILETYPE.get(file_type, "application/octet-stream")
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _ai_analysis_placeholder(document_id: uuid.UUID) -> None:
    """Placeholder for the Phase-4 AI analysis queue trigger.

    Intentionally a no-op for now (Zero-Knowledge: auditors never see analytics).
    """
    return None


@router.get("/next", response_model=CertificationDocOut)
async def next_document(
    user: User = Depends(require_role("auditor", "manager", "gm", "owner", "admin")),
    session: AsyncSession = Depends(get_session),
) -> CertificationDocOut:
    doc = (
        await session.execute(
            select(Document)
            .where(
                Document.company_id == user.company_id,
                Document.status == DocStatus.ocr_processing,
            )
            .order_by(Document.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=MSG_NONE_PENDING)

    # Decrypt original for display (image only -> base64; pdf also supported).
    image_url: str | None = None
    if doc.file_type in (FileType.image, FileType.pdf):
        try:
            raw = await load_decrypted(
                relative_path=doc.file_path,
                company_id=str(doc.company_id),
                file_uuid=str(doc.id),
            )
            image_url = _data_url(doc.file_type, raw)
            del raw
        except FileNotFoundError:
            image_url = None

    return CertificationDocOut(
        document_id=doc.id,
        original_filename=doc.original_filename,
        file_type=doc.file_type.value,
        doc_category=doc.doc_category.value,
        confidence_score=float(doc.confidence_score) if doc.confidence_score is not None else None,
        original_image_url=image_url,
        extracted_data=doc.extracted_data,
    )


@router.post("/{doc_id}/certify", response_model=CertifyResponse)
async def certify_document(
    doc_id: uuid.UUID,
    body: CertifyRequest,
    user: User = Depends(require_role("auditor", "manager", "gm", "owner", "admin")),
    session: AsyncSession = Depends(get_session),
) -> CertifyResponse:
    doc = (
        await session.execute(select(Document).where(Document.id == doc_id))
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=MSG_NOT_FOUND)
    if doc.company_id != user.company_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=MSG_FORBIDDEN_COMPANY)
    if doc.status != DocStatus.ocr_processing:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=MSG_NOT_READY)

    # Snapshot the document BEFORE mutation (for the update ledger entry).
    doc_old = model_snapshot(doc, DOCUMENT_FIELDS)

    # Determine corrections vs. OCR values.
    existing = doc.extracted_data if isinstance(doc.extracted_data, dict) else {}
    ocr_fields = existing.get("fields", {}) if isinstance(existing, dict) else {}
    corrected = body.corrected_fields or {}

    corrections_made: dict = {}
    correction_reasons: list[str] = []
    for key, new_val in corrected.items():
        old_val = ocr_fields.get(key)
        if old_val != new_val:
            corrections_made[key] = {"from": old_val, "to": new_val}
            correction_reasons.append(correction_reason(key, old_val, new_val))

    # Persist the human-verified field values back into extracted_data.
    final_fields = dict(ocr_fields)
    final_fields.update(corrected)
    new_extracted = dict(existing)
    new_extracted["fields"] = final_fields
    new_extracted["certified_by_human"] = True
    doc.extracted_data = new_extracted

    # Create the certification record.
    cert = DocumentCertification(
        document_id=doc.id,
        auditor_id=user.id,
        corrections_made=corrections_made or None,
        is_valid=body.is_valid,
    )
    session.add(cert)
    await session.flush()  # get cert.id

    # Mark certified; human verification => confidence 100.
    doc.status = DocStatus.certified
    doc.confidence_score = Decimal("100.00")

    # --- Auto-ledger (hash-chained) ---
    # 1. Document update (status -> certified, corrections applied).
    cert_reason = "اعتماد مستند"
    if correction_reasons:
        cert_reason = "اعتماد مستند | " + " ؛ ".join(correction_reasons)
    await log_document_update(
        session, doc, old=doc_old, created_by=user.id, reason=cert_reason
    )
    # 2. Certification insert (this entry's hash is returned to the client).
    entry = await log_certification_insert(
        session, cert, created_by=user.id, reason=cert_reason
    )

    await session.commit()

    # Placeholder: enqueue AI analysis (no-op for now).
    _ai_analysis_placeholder(doc.id)

    return CertifyResponse(
        document_id=doc.id,
        certification_id=cert.id,
        status=doc.status.value,
        ledger_hash=entry.current_hash,
    )
