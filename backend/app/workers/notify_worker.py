"""Celery tasks for notifications: daily digest + WhatsApp queue flush."""
from __future__ import annotations

import asyncio

from app.database import AsyncSessionLocal, set_user_role
from app.services import whatsapp
from app.services.digest_service import generate_and_send_digests


async def _digest_async() -> dict:
    async with AsyncSessionLocal() as session:
        await set_user_role(session, "admin")  # non-auditor for RLS writes
        return await generate_and_send_digests(session)


def run_daily_digest_sync() -> dict:
    return asyncio.run(_digest_async())


def flush_whatsapp_sync() -> dict:
    return asyncio.run(whatsapp.flush_queue())


try:  # pragma: no cover - depends on celery availability
    from app.celery_app import celery_app

    @celery_app.task(name="notify.daily_digest")
    def daily_digest_task() -> dict:
        return run_daily_digest_sync()

    @celery_app.task(name="notify.flush_whatsapp_queue")
    def flush_whatsapp_queue_task() -> dict:
        return flush_whatsapp_sync()

except Exception:  # noqa: BLE001
    celery_app = None  # type: ignore
    daily_digest_task = None  # type: ignore
    flush_whatsapp_queue_task = None  # type: ignore
