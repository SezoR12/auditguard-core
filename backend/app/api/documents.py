"""Document ingestion API: secure upload + listing.

All uploads are validated, encrypted with AES-256-GCM, and persisted to the
local Smart Box volume. Only metadata is stored in the database.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.config import settings
from app.database import get_session
from app.models import Document, User
from app.models.enums import DocStatus, FileType
from app.schemas.document import (
    ALLOWED_CATEGORY_KEYS,
    CATEGORY_KEY_TO_ENUM,
    DocumentOut,
    UploadResponse,
)
from app.storage import save_encrypted
from app.validation import validate_upload

router = APIRouter(prefix="/documents", tags=["documents"])

# Arabic messages
MSG_TOO_LARGE = "حجم الملف يتجاوز الحد الأقصى المسموح (50 ميغابايت)"
MSG_EMPTY = "الملف فارغ"
MSG_BAD_EXT = "نوع الملف غير مدعوم. الأنواع المسموحة: xlsx, csv, docx, jpg, jpeg, png, tiff, pdf, json"
MSG_MIME_MISMATCH = "محتوى الملف لا يطابق امتداده — تم رفض الملف لأسباب أمنية"
MSG_BAD_CATEGORY = "تصنيف المستند غير صالح"
MSG_BAD_BRANCH = "الفرع غير صالح"
MSG_BAD_ENCRYPTED_JSON = (
    "ملف JSON المشفر غير صالح: يجب أن يحتوي على المفتاحين 'metadata' و'encrypted_payload'"
)


def _validate_encrypted_json(data: bytes) -> dict:
    """Ensure an encrypted-JSON upload has the expected envelope. Does NOT decrypt."""
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=MSG_BAD_ENCRYPTED_JSON)
    if not isinstance(parsed, dict) or "metadata" not in parsed or "encrypted_payload" not in parsed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=MSG_BAD_ENCRYPTED_JSON)
    return parsed


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_category: str = Form(...),
    branch_id: str | None = Form(None),
    user: User = Depends(require_role("auditor", "manager", "gm", "owner", "admin")),
    session: AsyncSession = Depends(get_session),
) -> UploadResponse:
    # --- category ---
    if doc_category not in ALLOWED_CATEGORY_KEYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=MSG_BAD_CATEGORY)
    category_enum = CATEGORY_KEY_TO_ENUM[doc_category]

    # --- branch (optional) ---
    branch_uuid: uuid.UUID | None = None
    if branch_id:
        try:
            branch_uuid = uuid.UUID(branch_id)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=MSG_BAD_BRANCH)

    # --- read bytes (size guard) ---
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=MSG_EMPTY)
    if len(data) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=MSG_TOO_LARGE
        )

    # --- validate extension + MIME (virus-scan simulation) ---
    try:
        file_type, detected_mime = validate_upload(file.filename or "", data)
    except ValueError as exc:
        reason = str(exc)
        if reason == "extension_not_allowed":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=MSG_BAD_EXT)
        # mime_mismatch:<detected>
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=MSG_MIME_MISMATCH)

    # --- encrypted-JSON special pipeline (validate envelope, store flagged) ---
    extracted: dict = {"category_key": doc_category, "detected_mime": detected_mime}
    if file_type == FileType.encrypted_json:
        envelope = _validate_encrypted_json(data)
        extracted["encrypted_json"] = True
        extracted["json_metadata"] = envelope.get("metadata")

    # --- encrypt + persist ---
    file_uuid = uuid.uuid4()
    company_id = str(user.company_id)
    rel_path = await save_encrypted(
        plaintext=data,
        company_id=company_id,
        file_uuid=str(file_uuid),
        filename=file.filename or "file",
    )

    # --- create DB record ---
    doc = Document(
        id=file_uuid,
        file_path=rel_path,
        original_filename=file.filename or "file",
        file_type=file_type,
        doc_category=category_enum,
        status=DocStatus.pending,
        uploaded_by=user.id,
        company_id=user.company_id,
        branch_id=branch_uuid,
        ocr_status="not_started",
        extracted_data=extracted,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    # Trigger OCR for image/PDF documents (runs after response is sent).
    if file_type in (FileType.image, FileType.pdf):
        from app.workers.ocr_worker import process_document

        background_tasks.add_task(process_document, doc.id)

    return UploadResponse(
        document_id=doc.id,
        status=doc.status,
        file_type=doc.file_type,
        doc_category=doc.doc_category,
        original_filename=doc.original_filename,
    )


@router.get("/my-uploads", response_model=list[DocumentOut])
async def my_uploads(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Document]:
    """Documents uploaded by the current user, newest first."""
    rows = (
        await session.execute(
            select(Document)
            .where(Document.uploaded_by == user.id)
            .order_by(Document.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


@router.get("/pending-certification", response_model=list[DocumentOut])
async def pending_certification(
    user: User = Depends(require_role("auditor", "manager", "gm", "owner", "admin")),
    session: AsyncSession = Depends(get_session),
) -> list[Document]:
    """Documents in the user's company awaiting OCR/certification (pending or ocr_processing)."""
    rows = (
        await session.execute(
            select(Document)
            .where(
                Document.company_id == user.company_id,
                Document.status.in_([DocStatus.pending, DocStatus.ocr_processing]),
            )
            .order_by(Document.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


@router.get("/company", response_model=list[DocumentOut])
async def company_documents(
    user: User = Depends(require_role("owner", "gm", "manager", "admin")),
    session: AsyncSession = Depends(get_session),
) -> list[Document]:
    """All documents for the user's company (owner/management scope), newest first."""
    rows = (
        await session.execute(
            select(Document)
            .where(Document.company_id == user.company_id)
            .order_by(Document.created_at.desc())
        )
    ).scalars().all()
    return list(rows)
