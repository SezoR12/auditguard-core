"""Schemas for notifications + daily digests."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: uuid.UUID
    severity: str
    category: str
    title: str
    body: str
    financial_impact: float | None = None
    link: dict[str, Any] | None = None
    ref_type: str | None = None
    ref_id: uuid.UUID | None = None
    is_read: bool
    created_at: datetime


class NotificationListOut(BaseModel):
    unread_count: int
    items: list[NotificationOut]


class MarkReadResponse(BaseModel):
    updated: int


class DailyDigestOut(BaseModel):
    id: uuid.UUID
    digest_date: date
    waste_total_iqd: float
    tasks_completed: int
    tasks_overdue: int
    alerts_open: int
    trust_index: int | None = None
    message: str
    whatsapp_sent: bool
    created_at: datetime
