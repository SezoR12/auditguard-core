"""Celery tasks for the task engine: daily generation + overdue checks.

Schedules (Celery Beat, see app/celery_app.py):
  - tasks.generate_daily   → 08:00 Asia/Baghdad every day
  - tasks.check_overdue    → every 15 minutes
"""
from __future__ import annotations

import asyncio

from app.database import AsyncSessionLocal, set_user_role
from app.services import performance
from app.services.task_generator import generate_daily


async def _generate_daily_async() -> dict:
    async with AsyncSessionLocal() as session:
        # Privileged role for RLS (not an auditor).
        await set_user_role(session, "admin")
        return await generate_daily(session)


async def _check_overdue_async() -> dict:
    async with AsyncSessionLocal() as session:
        await set_user_role(session, "admin")
        return await performance.check_overdue(session)


def run_generate_daily_sync() -> dict:
    return asyncio.run(_generate_daily_async())


def run_check_overdue_sync() -> dict:
    return asyncio.run(_check_overdue_async())


# --- Celery task registration ----------------------------------------------
try:  # pragma: no cover - depends on celery availability
    from app.celery_app import celery_app

    @celery_app.task(name="tasks.generate_daily")
    def generate_daily_task() -> dict:
        return run_generate_daily_sync()

    @celery_app.task(name="tasks.check_overdue")
    def check_overdue_task() -> dict:
        return run_check_overdue_sync()

except Exception:  # noqa: BLE001
    celery_app = None  # type: ignore
    generate_daily_task = None  # type: ignore
    check_overdue_task = None  # type: ignore
