"""OCR background worker.

Processes a document whose status is 'pending' and whose file_type is image
or pdf:
  1. Load the encrypted file and decrypt it IN MEMORY (never to disk).
  2. Run Tesseract OCR (Arabic + English).
  3. Parse invoice fields, compute confidence, color-code each field.
  4. Persist extracted_data + confidence_score, set status -> 'ocr_processing'.

It can be invoked two ways:
  * `await process_document(doc_id)` — direct async call (used as a FastAPI
    BackgroundTask right after upload), and
  * `run_ocr_for_document.delay(doc_id)` — Celery task (when a broker is wired).
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.database import AsyncSessionLocal, set_user_role
from app.models import Document
from app.models.enums import DocStatus, FileType
from app.ocr import build_extracted_data, parse_fields, run_ocr
from app.storage import load_decrypted

OCR_FILE_TYPES = {FileType.image, FileType.pdf}


def _per_field_confidence(fields: dict, overall: float) -> dict[str, float | None]:
    """Assign each present field the overall OCR confidence; missing -> None.

    Tesseract gives a single page-level confidence; we attribute it to fields
    we successfully parsed and leave missing fields without a score (-> red).
    """
    out: dict[str, float | None] = {}
    for key in ("invoice_number", "date", "amount", "vendor_name", "items_list"):
        val = fields.get(key)
        present = val not in (None, "", [], {})
        out[key] = overall if present else None
    return out


async def process_document(doc_id: uuid.UUID | str) -> dict:
    """Run OCR for a single document. Returns a small status dict."""
    doc_uuid = uuid.UUID(str(doc_id))

    async with AsyncSessionLocal() as session:
        # Worker runs with a privileged role for RLS (not an auditor).
        await set_user_role(session, "admin")

        doc = (
            await session.execute(select(Document).where(Document.id == doc_uuid))
        ).scalar_one_or_none()
        if doc is None:
            return {"ok": False, "reason": "not_found"}
        if doc.file_type not in OCR_FILE_TYPES:
            return {"ok": False, "reason": "unsupported_file_type"}
        if doc.status != DocStatus.pending:
            return {"ok": False, "reason": f"status_is_{doc.status.value}"}

        # 1. Decrypt in memory.
        file_bytes = await load_decrypted(
            relative_path=doc.file_path,
            company_id=str(doc.company_id),
            file_uuid=str(doc.id),
        )

        # 2 + 3. OCR + parse.
        text, overall_conf = run_ocr(file_bytes, doc.file_type.value, lang="ara+eng")
        # Discard decrypted bytes ASAP.
        del file_bytes

        fields = parse_fields(text)
        field_conf = _per_field_confidence(fields, overall_conf)
        extracted = build_extracted_data(fields, field_conf, overall_conf, raw_text=text)
        # Preserve any prior metadata (e.g. category_key) from upload.
        if isinstance(doc.extracted_data, dict):
            merged = dict(doc.extracted_data)
            merged.update(extracted)
            extracted = merged

        # 4. Persist.
        doc.extracted_data = extracted
        doc.confidence_score = Decimal(str(round(overall_conf, 2)))
        doc.ocr_status = "completed"
        doc.status = DocStatus.ocr_processing
        await session.commit()

    return {"ok": True, "document_id": str(doc_uuid), "confidence": overall_conf}


def process_document_sync(doc_id: uuid.UUID | str) -> dict:
    """Synchronous wrapper for Celery / CLI usage."""
    return asyncio.run(process_document(doc_id))


# --- Celery task registration -----------------------------------------------
# Importing the central app here registers this task at worker startup
# (app.celery_app includes this module). Guarded so that importing the worker
# module in environments without celery installed (e.g. unit tests) still works.
try:  # pragma: no cover - depends on celery availability
    from app.celery_app import celery_app

    @celery_app.task(name="ocr.run_ocr_for_document", bind=True, max_retries=3)
    def run_ocr_for_document(self, doc_id: str) -> dict:  # noqa: ANN001
        try:
            return process_document_sync(doc_id)
        except Exception as exc:  # noqa: BLE001
            # Retry with exponential backoff on transient failures.
            raise self.retry(exc=exc, countdown=min(60, 2 ** self.request.retries))

except Exception:  # noqa: BLE001
    celery_app = None  # type: ignore
    run_ocr_for_document = None  # type: ignore


def enqueue_ocr(doc_id: uuid.UUID | str) -> str | None:
    """Enqueue OCR via Celery. Returns the task id, or None if unavailable.

    Used by the upload endpoint. If Celery/broker is not reachable, the caller
    can fall back to running OCR inline (FastAPI BackgroundTask).
    """
    if run_ocr_for_document is None:
        return None
    try:
        result = run_ocr_for_document.delay(str(doc_id))
        return result.id
    except Exception:  # noqa: BLE001 - broker unreachable, etc.
        return None

