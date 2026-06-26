"""Task engine API: auditor task list, completion, overdue check, generation."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.database import get_session
from app.models import AuditorPerformance, AuditTask, User
from app.models.enums import TaskStatus
from app.schemas.tasks import (
    GenerateResponse,
    OverdueCheckResponse,
    TaskCompleteResponse,
    TaskOut,
)
from app.services import performance, sla
from app.services.task_generator import generate_daily

router = APIRouter(prefix="/tasks", tags=["tasks"])

MSG_NOT_FOUND = "المهمة غير موجودة"
MSG_NOT_OWNER = "لا يمكنك إنجاز مهمة ليست مخصصة لك"
MSG_ALREADY_DONE = "المهمة منجزة مسبقاً"


def _baghdad_day_bounds_utc(ref_bg: datetime) -> tuple[datetime, datetime]:
    """Return [start, end) of the Baghdad day containing ref_bg, in UTC."""
    start_bg = ref_bg.replace(hour=0, minute=0, second=0, microsecond=0)
    end_bg = start_bg + timedelta(days=1)
    return start_bg.astimezone(timezone.utc), end_bg.astimezone(timezone.utc)


@router.get("/my-tasks", response_model=list[TaskOut])
async def my_tasks(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TaskOut]:
    """Today's tasks (Baghdad day) for the logged-in auditor, with countdown."""
    now_bg = sla.now_baghdad()
    start_utc, end_utc = _baghdad_day_bounds_utc(now_bg)

    rows = (
        await session.execute(
            select(AuditTask)
            .where(
                and_(
                    AuditTask.auditor_id == user.id,
                    AuditTask.created_at >= start_utc,
                    AuditTask.created_at < end_utc,
                )
            )
            .order_by(AuditTask.sla_deadline.asc().nulls_last())
        )
    ).scalars().all()

    now_utc = datetime.now(timezone.utc)
    out: list[TaskOut] = []
    for t in rows:
        item = TaskOut.model_validate(t)
        item.task_type = t.task_type.value if hasattr(t.task_type, "value") else str(t.task_type)
        item.status = t.status.value if hasattr(t.status, "value") else str(t.status)
        item.time_remaining_seconds = sla.seconds_remaining(t.sla_deadline, now_utc)
        if t.status == TaskStatus.completed:
            item.time_color = "green"
        else:
            item.time_color = sla.time_color(t.sla_deadline, t.created_at, now_utc)
        out.append(item)
    return out


@router.post("/{task_id}/complete", response_model=TaskCompleteResponse)
async def complete_task(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TaskCompleteResponse:
    task = (
        await session.execute(select(AuditTask).where(AuditTask.id == task_id))
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=MSG_NOT_FOUND)
    if task.auditor_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=MSG_NOT_OWNER)
    if task.status == TaskStatus.completed:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=MSG_ALREADY_DONE)

    now_utc = datetime.now(timezone.utc)
    deadline = task.sla_deadline
    if deadline is not None and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    on_time = deadline is None or now_utc <= deadline

    task.status = TaskStatus.completed
    task.completed_at = now_utc

    await performance.record_task_completed(session, user, task, on_time=on_time)
    await session.commit()

    return TaskCompleteResponse(
        task_id=task.id,
        status=task.status.value,
        completed_at=now_utc,
        on_time=on_time,
    )


@router.get("/overdue-check", response_model=OverdueCheckResponse)
async def overdue_check(
    user: User = Depends(require_role("admin", "appowner", "owner")),
    session: AsyncSession = Depends(get_session),
) -> OverdueCheckResponse:
    """Internal endpoint (also called by Celery Beat) to penalize overdue tasks."""
    result = await performance.check_overdue(session)
    return OverdueCheckResponse(**result)


@router.post("/generate-daily", response_model=GenerateResponse)
async def generate_daily_endpoint(
    user: User = Depends(require_role("admin", "appowner", "owner")),
    session: AsyncSession = Depends(get_session),
) -> GenerateResponse:
    """Internal/admin endpoint to trigger daily task generation."""
    # Owners generate for their own company; admins/appowner for all.
    company_id = user.company_id if user.role.value == "owner" else None
    result = await generate_daily(session, company_id=company_id)
    return GenerateResponse(**result)
