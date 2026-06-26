"""Celery tasks for the AI analysis engine (the Silent Engine).

Schedule (Celery Beat): analysis.run_daily at 02:00 Asia/Baghdad (23:00 UTC).
"""
from __future__ import annotations

import asyncio

from app.ai.orchestrator import run_analysis_all_companies, run_analysis_for_company


def run_analysis_for_company_sync(company_id: str) -> dict:
    return asyncio.run(run_analysis_for_company(company_id))


def run_daily_analysis_sync() -> dict:
    return asyncio.run(run_analysis_all_companies())


# --- Celery task registration ----------------------------------------------
try:  # pragma: no cover - depends on celery availability
    from app.celery_app import celery_app

    @celery_app.task(name="analysis.run_for_company")
    def run_analysis_for_company_task(company_id: str) -> dict:
        return run_analysis_for_company_sync(company_id)

    @celery_app.task(name="analysis.run_daily")
    def run_daily_analysis_task() -> dict:
        return run_daily_analysis_sync()

except Exception:  # noqa: BLE001
    celery_app = None  # type: ignore
    run_analysis_for_company_task = None  # type: ignore
    run_daily_analysis_task = None  # type: ignore
