"""Admin endpoints for triggering background analysis (testing/manual runs)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.database import get_session
from app.models import User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/run-analysis")
async def run_analysis(
    company_id: uuid.UUID | None = Query(None),
    inline: bool = Query(True, description="Run synchronously (true) or enqueue via Celery (false)"),
    user: User = Depends(require_role("admin", "appowner", "owner")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Trigger the AI analysis pipeline.

    - owner: scoped to their own company.
    - admin/appowner: may pass company_id, or omit to run all companies.
    `inline=true` runs in-process (handy for tests); otherwise enqueues Celery.
    """
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    target = user.company_id if role == "owner" else company_id

    if inline:
        from app.ai.orchestrator import (
            run_analysis_all_companies,
            run_analysis_for_company,
        )

        if target is not None:
            return await run_analysis_for_company(target)
        return await run_analysis_all_companies()

    # Enqueue via Celery.
    from app.workers.analysis_worker import (
        run_analysis_for_company_task,
        run_daily_analysis_task,
    )

    if target is not None and run_analysis_for_company_task is not None:
        res = run_analysis_for_company_task.delay(str(target))
        return {"enqueued": True, "task_id": res.id, "company_id": str(target)}
    if run_daily_analysis_task is not None:
        res = run_daily_analysis_task.delay()
        return {"enqueued": True, "task_id": res.id, "scope": "all_companies"}
    return {"enqueued": False, "reason": "celery_unavailable"}
