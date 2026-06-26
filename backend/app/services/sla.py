"""SLA, demerit, and efficiency pure-logic helpers (no DB, easily testable).

Timezone: Asia/Baghdad (UTC+3, no DST).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.enums import TaskType

# Baghdad is UTC+3 year-round (no daylight saving).
BAGHDAD_TZ = timezone(timedelta(hours=3))

# SLA durations (hours) per task type.
SLA_HOURS: dict[str, float] = {
    "ocr_certification": 4.0,
    "bank_statement": 24.0,
    "reversal": 2.0,
    "backlog": 8.0,
    "custom": 8.0,
}
DEFAULT_SLA_HOURS = 8.0

# Which generated task kinds are "critical" (higher demerit on overdue).
CRITICAL_KINDS = {"reversal"}

# Demerit point values.
DEMERIT_CRITICAL = 3
DEMERIT_NORMAL = 1


def now_baghdad() -> datetime:
    """Current time in Baghdad timezone (aware)."""
    return datetime.now(BAGHDAD_TZ)


def sla_deadline(generated_at: datetime, kind: str, custom_hours: float | None = None) -> datetime:
    """Compute the SLA deadline for a task kind from its generation time."""
    if custom_hours is not None:
        hours = custom_hours
    else:
        hours = SLA_HOURS.get(kind, DEFAULT_SLA_HOURS)
    return generated_at + timedelta(hours=hours)


def is_critical_kind(kind: str) -> bool:
    return kind in CRITICAL_KINDS


def demerit_for(is_critical: bool) -> int:
    """Demerit points to apply when a task goes overdue."""
    return DEMERIT_CRITICAL if is_critical else DEMERIT_NORMAL


def seconds_remaining(deadline: datetime | None, ref: datetime | None = None) -> int | None:
    """Whole seconds until `deadline`. Negative if past. None if no deadline."""
    if deadline is None:
        return None
    ref = ref or datetime.now(timezone.utc)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return int((deadline - ref).total_seconds())


def time_color(deadline: datetime | None, created_at: datetime | None, ref: datetime | None = None) -> str:
    """Color code: 'green' on track, 'yellow' < 50% time left, 'red' overdue.

    Based on the fraction of the total SLA window remaining.
    """
    if deadline is None:
        return "green"
    ref = ref or datetime.now(timezone.utc)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    remaining = (deadline - ref).total_seconds()
    if remaining <= 0:
        return "red"
    if created_at is not None:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        total = (deadline - created_at).total_seconds()
        if total > 0 and (remaining / total) < 0.5:
            return "yellow"
    return "green"


def efficiency_score(tasks_completed_on_time: int, total_tasks: int, total_demerits: int) -> float:
    """efficiency = (on_time / total) * 100 - (demerits * 5). Clamped to [0, 100]."""
    if total_tasks <= 0:
        base = 0.0
    else:
        base = (tasks_completed_on_time / total_tasks) * 100.0
    score = base - (total_demerits * 5)
    return round(max(0.0, min(100.0, score)), 2)


# Map a generated task "kind" to the stored TaskType enum (the enum is fixed).
KIND_TO_TASKTYPE: dict[str, TaskType] = {
    "ocr_certification": TaskType.document_review,
    "bank_statement": TaskType.reconciliation,
    "reversal": TaskType.investigation,
    "backlog": TaskType.other,
    "custom": TaskType.other,
}


def kind_to_task_type(kind: str) -> TaskType:
    return KIND_TO_TASKTYPE.get(kind, TaskType.other)
