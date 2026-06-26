"""Daily task generator.

For each active auditor, generates tasks from real backlog signals:
  - pending OCR certifications (documents in 'pending'/'ocr_processing')
  - missing bank statements for the previous month
  - reverse entries needing verification (audit_ledger action='reverse')
  - branch-specific backlog

Runs at 08:00 Asia/Baghdad via Celery Beat, or via POST /tasks/generate-daily.
Idempotent per day: it won't duplicate an auto-generated task kind for an
auditor that already has an open one created today.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLedger, Document, User
from app.models.enums import DocCategory, DocStatus, TaskStatus, UserRole
from app.services import sla


def _title_ocr(count: int) -> str:
    return f"تحقق من {count} فاتورة مصورة"


def _title_bank(month_name: str) -> str:
    return f"ارفع كشوفات حساب بنكي لشهر {month_name}"


def _title_reversal(branch_name: str) -> str:
    return f"مراجعة قيد معاكس لفرع {branch_name}"


def _title_backlog(count: int) -> str:
    return f"معالجة {count} مهمة متراكمة"


_AR_MONTHS = {
    1: "كانون الثاني", 2: "شباط", 3: "آذار", 4: "نيسان", 5: "مايو", 6: "حزيران",
    7: "تموز", 8: "آب", 9: "أيلول", 10: "تشرين الأول", 11: "تشرين الثاني", 12: "كانون الأول",
}


async def _already_generated_today(
    session: AsyncSession, auditor_id: uuid.UUID, title_prefix: str, day_start_utc
) -> bool:
    from app.models import AuditTask

    existing = (
        await session.execute(
            select(func.count())
            .select_from(AuditTask)
            .where(
                and_(
                    AuditTask.auditor_id == auditor_id,
                    AuditTask.created_at >= day_start_utc,
                    AuditTask.title.like(f"{title_prefix}%"),
                )
            )
        )
    ).scalar_one()
    return existing > 0


async def generate_for_auditor(
    session: AsyncSession, auditor: User, *, now_baghdad=None
) -> list:
    """Generate today's tasks for one auditor. Returns the created AuditTask rows."""
    from app.models import AuditTask

    now_bg = now_baghdad or sla.now_baghdad()
    now_utc = now_bg.astimezone(sla.timezone.utc)
    day_start_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        hours=3
    )  # start of Baghdad day, expressed in UTC

    created: list = []

    def _add(kind: str, title: str):
        is_crit = sla.is_critical_kind(kind)
        task = AuditTask(
            auditor_id=auditor.id,
            title=title,
            task_type=sla.kind_to_task_type(kind),
            status=TaskStatus.pending,
            is_critical=is_crit,
            sla_deadline=sla.sla_deadline(now_utc, kind),
        )
        session.add(task)
        created.append(task)

    # --- 1. Pending OCR certifications in the auditor's company ---
    pending_docs = (
        await session.execute(
            select(func.count())
            .select_from(Document)
            .where(
                Document.company_id == auditor.company_id,
                Document.status.in_([DocStatus.pending, DocStatus.ocr_processing]),
            )
        )
    ).scalar_one()
    if pending_docs > 0 and not await _already_generated_today(
        session, auditor.id, "تحقق من", day_start_utc
    ):
        _add("ocr_certification", _title_ocr(pending_docs))

    # --- 2. Missing bank statements for the previous month ---
    prev_month = (now_bg.month - 1) or 12
    month_name = _AR_MONTHS[prev_month]
    has_statement = (
        await session.execute(
            select(func.count())
            .select_from(Document)
            .where(
                Document.company_id == auditor.company_id,
                Document.doc_category == DocCategory.statement,
            )
        )
    ).scalar_one()
    if has_statement == 0 and not await _already_generated_today(
        session, auditor.id, "ارفع كشوفات", day_start_utc
    ):
        _add("bank_statement", _title_bank(month_name))

    # --- 3. Reverse entries needing verification ---
    reversals = (
        await session.execute(
            select(func.count())
            .select_from(AuditLedger)
            .where(AuditLedger.action == "reverse")
        )
    ).scalar_one()
    if reversals > 0 and not await _already_generated_today(
        session, auditor.id, "مراجعة قيد معاكس", day_start_utc
    ):
        branch_name = "الرئيسي"
        _add("reversal", _title_reversal(branch_name))

    return created


async def generate_daily(session: AsyncSession, *, company_id: uuid.UUID | None = None) -> dict:
    """Generate tasks for all active auditors (optionally scoped to a company)."""
    q = select(User).where(User.is_active.is_(True), User.role == UserRole.auditor)
    if company_id is not None:
        q = q.where(User.company_id == company_id)
    auditors = (await session.execute(q)).scalars().all()

    total = 0
    per_auditor: dict[str, int] = {}
    for auditor in auditors:
        tasks = await generate_for_auditor(session, auditor)
        per_auditor[str(auditor.id)] = len(tasks)
        total += len(tasks)

    await session.commit()
    return {"auditors": len(auditors), "tasks_created": total, "per_auditor": per_auditor}
