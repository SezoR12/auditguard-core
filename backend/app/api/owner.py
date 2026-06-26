"""Owner oversight endpoints (preview; full dashboard in Phase 7)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.database import get_session
from app.models import AuditorPerformance, User
from app.models.enums import UserRole
from app.schemas.tasks import AuditorPerformanceOut
from app.services import sla

router = APIRouter(prefix="/owner", tags=["owner"])


@router.get("/auditor-performance", response_model=list[AuditorPerformanceOut])
async def auditor_performance(
    user: User = Depends(require_role("owner", "gm", "admin", "appowner")),
    session: AsyncSession = Depends(get_session),
) -> list[AuditorPerformanceOut]:
    """Today's performance for every auditor in the owner's company."""
    today = sla.now_baghdad().date()

    auditors = (
        await session.execute(
            select(User).where(
                User.company_id == user.company_id,
                User.role == UserRole.auditor,
                User.is_active.is_(True),
            )
        )
    ).scalars().all()

    # Map auditor_id -> today's performance row.
    perf_rows = (
        await session.execute(
            select(AuditorPerformance).where(
                and_(
                    AuditorPerformance.company_id == user.company_id,
                    AuditorPerformance.perf_date == today,
                )
            )
        )
    ).scalars().all()
    perf_by_auditor = {p.auditor_id: p for p in perf_rows}

    out: list[AuditorPerformanceOut] = []
    for a in auditors:
        p = perf_by_auditor.get(a.id)
        out.append(
            AuditorPerformanceOut(
                auditor_id=a.id,
                full_name=a.full_name,
                tasks_completed_today=p.tasks_completed if p else 0,
                tasks_delayed=p.tasks_delayed if p else 0,
                demerit_points=p.demerit_points if p else 0,
                efficiency_score=float(p.efficiency_score) if p else 0.0,
            )
        )
    return out
