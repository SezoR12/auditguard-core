"""Service-layer auto-logging helpers for critical tables.

We use explicit service-layer calls rather than SQLAlchemy ORM events because:
  * the engine is async (ORM events can't `await` an INSERT into the ledger), and
  * the acting user (`created_by`) and the RLS role live in the request context,
    not in the ORM flush.

These helpers serialize a model row to a JSON-safe dict and append a
hash-chained ledger entry via app.services.ledger_service.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LedgerAction
from app.services.ledger_service import append_ledger_entry


def to_jsonable(value: Any) -> Any:
    """Recursively convert ORM/Python values into JSON-serializable primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (uuid.UUID,)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "value"):  # Enum
        return value.value
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    return str(value)


def model_snapshot(obj: Any, fields: list[str]) -> dict:
    """Snapshot selected fields of an ORM object into a JSON-safe dict."""
    return {f: to_jsonable(getattr(obj, f, None)) for f in fields}


DOCUMENT_FIELDS = [
    "id", "original_filename", "file_type", "doc_category", "status",
    "uploaded_by", "company_id", "branch_id", "ocr_status", "confidence_score",
]
CERTIFICATION_FIELDS = [
    "id", "document_id", "auditor_id", "is_valid", "corrections_made",
]
TASK_FIELDS = [
    "id", "auditor_id", "title", "task_type", "status", "is_critical",
    "completed_at", "demerit_points",
]


async def log_document_insert(
    session: AsyncSession, document, *, created_by: uuid.UUID
):
    return await append_ledger_entry(
        session,
        table_name="documents",
        record_id=document.id,
        action=LedgerAction.insert,
        created_by=created_by,
        new_value=model_snapshot(document, DOCUMENT_FIELDS),
        reason="رفع مستند جديد",
    )


async def log_document_update(
    session: AsyncSession, document, *, old: dict, created_by: uuid.UUID, reason: str | None = None
):
    return await append_ledger_entry(
        session,
        table_name="documents",
        record_id=document.id,
        action=LedgerAction.update,
        created_by=created_by,
        old_value=old,
        new_value=model_snapshot(document, DOCUMENT_FIELDS),
        reason=reason or "تحديث مستند",
    )


async def log_certification_insert(
    session: AsyncSession, cert, *, created_by: uuid.UUID, reason: str | None = None
):
    return await append_ledger_entry(
        session,
        table_name="document_certifications",
        record_id=cert.id,
        action=LedgerAction.insert,
        created_by=created_by,
        new_value=model_snapshot(cert, CERTIFICATION_FIELDS),
        reason=reason or "اعتماد مستند",
    )


async def log_task_status_change(
    session: AsyncSession, task, *, old_status: str, created_by: uuid.UUID
):
    return await append_ledger_entry(
        session,
        table_name="audit_tasks",
        record_id=task.id,
        action=LedgerAction.update,
        created_by=created_by,
        old_value={"status": old_status},
        new_value=model_snapshot(task, TASK_FIELDS),
        reason=f"تغيير حالة المهمة من {old_status} إلى "
        f"{task.status.value if hasattr(task.status, 'value') else task.status}",
    )


def correction_reason(field: str, old: Any, new: Any) -> str:
    """Arabic reason string for an OCR correction (per spec)."""
    return f"تصحيح OCR: تغيير {field} من {old} إلى {new}"
