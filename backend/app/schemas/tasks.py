"""Schemas for the task engine."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    task_type: str
    status: str
    is_critical: bool
    sla_deadline: datetime | None = None
    completed_at: datetime | None = None
    demerit_points: int
    created_at: datetime
    # Derived (filled by the endpoint)
    time_remaining_seconds: int | None = None
    time_color: str = "green"


class TaskCompleteResponse(BaseModel):
    task_id: uuid.UUID
    status: str
    completed_at: datetime
    on_time: bool
    message: str = "تم إنجاز المهمة"


class GenerateResponse(BaseModel):
    auditors: int
    tasks_created: int
    per_auditor: dict[str, int]


class OverdueCheckResponse(BaseModel):
    overdue_tasks: int
    demerits_applied: int


class AuditorPerformanceOut(BaseModel):
    auditor_id: uuid.UUID
    full_name: str
    tasks_completed_today: int
    tasks_delayed: int
    demerit_points: int
    efficiency_score: float
