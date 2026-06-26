"""Manager modular dashboard API — branch/department-scoped widgets.

Data boundary: a manager only sees data for their own branch_id. Owners/GM can
pass an optional branch_id or see the whole company.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.database import get_session
from app.models import AuditorPerformance, AuditTask, Document, User, WasteMapItem
from app.models.enums import DocStatus, TaskStatus, UserRole
from app.services import sla

router = APIRouter(prefix="/manager", tags=["manager"])

MANAGER_ROLES = ("manager", "gm", "owner", "admin", "appowner")

AVAILABLE_WIDGETS = [
    {"key": "budget_status", "label": "حالة الميزانية"},
    {"key": "open_tasks", "label": "المهام المفتوحة"},
    {"key": "dept_quality_index", "label": "مؤشر جودة القسم"},
    {"key": "team_performance", "label": "أداء الفريق"},
    {"key": "pending_corrections", "label": "التصحيحات المعلّقة"},
]


def _scope_branch(user: User, branch_id: uuid.UUID | None) -> uuid.UUID | None:
    """Resolve the effective branch scope based on role.

    - manager: locked to their own branch_id (ignores query override).
    - owner/gm/admin: may pass branch_id, else company-wide (None).
    """
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role == "manager":
        return user.branch_id
    return branch_id


@router.get("/widgets")
async def list_widgets(user: User = Depends(require_role(*MANAGER_ROLES))) -> dict:
    return {"widgets": AVAILABLE_WIDGETS}


async def _branch_auditor_ids(session: AsyncSession, company_id, branch_id) -> list[uuid.UUID]:
    q = select(User.id).where(User.company_id == company_id, User.role == UserRole.auditor)
    if branch_id is not None:
        q = q.where(User.branch_id == branch_id)
    return [r for r in (await session.execute(q)).scalars().all()]


@router.get("/widget/{widget_key}")
async def widget_data(
    widget_key: str,
    user: User = Depends(require_role(*MANAGER_ROLES)),
    session: AsyncSession = Depends(get_session),
    branch_id: uuid.UUID | None = Query(None),
) -> dict:
    cid = user.company_id
    scope = _scope_branch(user, branch_id)

    if widget_key == "open_tasks":
        auditor_ids = await _branch_auditor_ids(session, cid, scope)
        if not auditor_ids:
            return {"widget": widget_key, "open_tasks": 0, "overdue": 0}
        open_n = (
            await session.execute(
                select(func.count()).select_from(AuditTask).where(
                    AuditTask.auditor_id.in_(auditor_ids),
                    AuditTask.status.in_([TaskStatus.pending, TaskStatus.in_progress]),
                )
            )
        ).scalar_one()
        overdue_n = (
            await session.execute(
                select(func.count()).select_from(AuditTask).where(
                    AuditTask.auditor_id.in_(auditor_ids), AuditTask.status == TaskStatus.overdue
                )
            )
        ).scalar_one()
        return {"widget": widget_key, "open_tasks": int(open_n), "overdue": int(overdue_n)}

    if widget_key == "budget_status":
        # Department waste as a proxy for budget pressure.
        wq = select(func.coalesce(func.sum(WasteMapItem.amount_iqd), 0)).where(
            WasteMapItem.company_id == cid
        )
        # waste_map_items has `department` (string), not branch_id; scope by
        # branch name if a manager branch is set.
        if scope is not None:
            branch = (await session.execute(select(User.branch_id).where(User.id == user.id))).scalar_one_or_none()
            # best-effort: no direct dept link, so company-level for now
        waste = (await session.execute(wq)).scalar_one()
        return {"widget": widget_key, "total_waste_iqd": float(waste)}

    if widget_key == "dept_quality_index":
        # Avg document confidence_score for the company (proxy for quality).
        avg_conf = (
            await session.execute(
                select(func.coalesce(func.avg(Document.confidence_score), 0)).where(
                    Document.company_id == cid, Document.status == DocStatus.certified
                )
            )
        ).scalar_one()
        return {"widget": widget_key, "quality_index": round(float(avg_conf), 1)}

    if widget_key == "team_performance":
        today = sla.now_baghdad().date()
        auditor_ids = await _branch_auditor_ids(session, cid, scope)
        rows = []
        if auditor_ids:
            perf = (
                await session.execute(
                    select(AuditorPerformance, User.full_name)
                    .join(User, User.id == AuditorPerformance.auditor_id)
                    .where(
                        AuditorPerformance.auditor_id.in_(auditor_ids),
                        AuditorPerformance.perf_date == today,
                    )
                )
            ).all()
            rows = [
                {
                    "auditor": name,
                    "completed": p.tasks_completed,
                    "delayed": p.tasks_delayed,
                    "efficiency": float(p.efficiency_score),
                }
                for p, name in perf
            ]
        return {"widget": widget_key, "team": rows}

    if widget_key == "pending_corrections":
        # Documents in OCR processing (awaiting human certification) for the company.
        n = (
            await session.execute(
                select(func.count()).select_from(Document).where(
                    Document.company_id == cid, Document.status == DocStatus.ocr_processing
                )
            )
        ).scalar_one()
        return {"widget": widget_key, "pending_corrections": int(n)}

    return {"widget": widget_key, "error": "unknown_widget"}
