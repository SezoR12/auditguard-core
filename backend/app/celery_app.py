"""Central Celery application for AuditCore background jobs.

Run the worker with:
    celery -A app.celery_app.celery_app worker --loglevel=info -Q ocr,tasks
Run the beat scheduler with:
    celery -A app.celery_app.celery_app beat --loglevel=info

Tasks live in app.workers.* and are auto-discovered via `include` below.
Redis is used as both broker and result backend (see settings.REDIS_URL).
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "auditcore",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.ocr_worker",
        "app.workers.task_worker",
        "app.workers.analysis_worker",
        "app.workers.notify_worker",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Don't let a stuck OCR job block a worker forever.
    task_time_limit=600,          # hard kill after 10 min
    task_soft_time_limit=540,     # soft (raises) at 9 min
    broker_connection_retry_on_startup=True,
    task_default_queue="ocr",
    task_routes={
        "ocr.run_ocr_for_document": {"queue": "ocr"},
        "tasks.generate_daily": {"queue": "tasks"},
        "tasks.check_overdue": {"queue": "tasks"},
        "analysis.run_daily": {"queue": "analysis"},
        "analysis.run_for_company": {"queue": "analysis"},
        "notify.daily_digest": {"queue": "notify"},
        "notify.flush_whatsapp_queue": {"queue": "notify"},
    },
)

# --- Celery Beat periodic schedule ------------------------------------------
# Baghdad is UTC+3 (no DST). 08:00 Baghdad == 05:00 UTC. We keep the worker on
# UTC and express the crontab in UTC to avoid ambiguity.
celery_app.conf.beat_schedule = {
    "generate-daily-tasks-08-baghdad": {
        "task": "tasks.generate_daily",
        # 05:00 UTC == 08:00 Asia/Baghdad
        "schedule": crontab(hour=5, minute=0),
        "options": {"queue": "tasks"},
    },
    "check-overdue-every-15min": {
        "task": "tasks.check_overdue",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "tasks"},
    },
    "run-daily-analysis-02-baghdad": {
        "task": "analysis.run_daily",
        # 23:00 UTC == 02:00 Asia/Baghdad (next day)
        "schedule": crontab(hour=23, minute=0),
        "options": {"queue": "analysis"},
    },
    "daily-digest-07-baghdad": {
        "task": "notify.daily_digest",
        # 04:00 UTC == 07:00 Asia/Baghdad
        "schedule": crontab(hour=4, minute=0),
        "options": {"queue": "notify"},
    },
    "flush-whatsapp-queue-5min": {
        "task": "notify.flush_whatsapp_queue",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "notify"},
    },
}
