"""Central Celery application for AuditCore background jobs.

The worker process starts with:
    celery -A app.celery_app.celery_app worker --loglevel=info --concurrency=2

Tasks live in app.workers.* and are auto-discovered via `include` below.
Redis is used as both broker and result backend (see settings.REDIS_URL).
"""
from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "auditcore",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.ocr_worker"],
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
    },
)
