"""Demerit application, performance aggregation, and overdue checking."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditorPerformance, AuditTask, User
from app.models.enums import TaskStatus
from app.services import sla


async def _get_or_create_perf(
    session: AsyncSession, auditor: User, perf_date: date
) -> AuditorPerformance:
    perf = (
        await session.execute(
            select(AuditorPerformance).where(
                and_(
                    AuditorPerformance.auditor_id == auditor.id,
                    AuditorPerformance.perf_date == perf_date,
                )
            )
        )
    ).scalar_one_or_none()
    if perf is None:
        perf = AuditorPerformance(
            auditor_id=auditor.id,
            company_id=auditor.company_id,
            perf_date=perf_date,
        )
        session.add(perf)
        await session.flush()
    return perf


def _recompute_efficiency(perf: AuditorPerformance) -> None:
    perf.efficiency_score = Decimal(
        str(
            sla.efficiency_score(
                perf.tasks_completed_on_time, perf.total_tasks, perf.demerit_points
            )
        )
    )


async def record_task_completed(
    session: AsyncSession, auditor: User, task: AuditTask, *, on_time: bool
) -> AuditorPerformance:
    """Update today's performance row when an auditor completes a task."""
    perf = await _get_or_create_perf(session, auditor, sla.now_baghdad().date())
    perf.tasks_completed += 1
    if on_time:
        perf.tasks_completed_on_time += 1
    # Ensure total reflects at least the tasks we know about.
    perf.total_tasks = max(perf.total_tasks, perf.tasks_completed + perf.tasks_delayed)
    _recompute_efficiency(perf)
    return perf


async def apply_overdue_demerit(
    session: AsyncSession, task: AuditTask, auditor: User
) -> int:
    """Apply demerit for one overdue task. Returns points applied."""
    points = sla.demerit_for(task.is_critical)
    old_status = task.status.value if hasattr(task.status, "value") else str(task.status)
    task.demerit_points += points
    task.status = TaskStatus.overdue

    # Auto-ledger: status change to overdue (system-applied; created_by=auditor).
    from app.services.audit_log import log_task_status_change

    await log_task_status_change(session, task, old_status=old_status, created_by=auditor.id)

    perf = await _get_or_create_perf(session, auditor, sla.now_baghdad().date())
    perf.demerit_points += points
    perf.tasks_delayed += 1
    perf.total_tasks = max(perf.total_tasks, perf.tasks_completed + perf.tasks_delayed)
    _recompute_efficiency(perf)
    return points


async def check_overdue(session: AsyncSession) -> dict:
    """Find tasks past their SLA that aren't completed/overdue and penalize them.

    Called every 15 minutes by Celery Beat (or POST /tasks/overdue-check).
    """
    now = datetime.now(timezone.utc)
    rows = (
        await session.execute(
            select(AuditTask, User)
            .join(User, User.id == AuditTask.auditor_id)
            .where(
                AuditTask.status.in_([TaskStatus.pending, TaskStatus.in_progress]),
                AuditTask.sla_deadline.is_not(None),
                AuditTask.sla_deadline < now,
            )
        )
    ).all()

    from app.services import alert_service

    total_points = 0
    affected = 0
    for task, auditor in rows:
        # Hours overdue before we flip status.
        deadline = task.sla_deadline
        if deadline is not None and deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        hours_overdue = (now - deadline).total_seconds() / 3600 if deadline else 0.0

        total_points += await apply_overdue_demerit(session, task, auditor)
        affected += 1

        # Notify owners/GM that this task is overdue (high severity).
        await alert_service.handle_task_overdue(
            session,
            company_id=auditor.company_id,
            auditor_name=auditor.full_name,
            task_title=task.title,
            hours_overdue=hours_overdue,
            ref_id=task.id,
        )

    await session.commit()
    return {"overdue_tasks": affected, "demerits_applied": total_points}
