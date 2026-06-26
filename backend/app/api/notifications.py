"""Owner notification center API + manual digest trigger."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.database import get_session
from app.models import DailyDigest, Notification, User
from app.schemas.notification import (
    DailyDigestOut,
    MarkReadResponse,
    NotificationListOut,
    NotificationOut,
)

router = APIRouter(prefix="/owner", tags=["notifications"])

OWNER_ROLES = ("owner", "gm", "admin", "appowner")


def _visible_filter(user: User):
    """Notifications addressed to this user OR broadcast (user_id NULL)."""
    return and_(
        Notification.company_id == user.company_id,
        or_(Notification.user_id == user.id, Notification.user_id.is_(None)),
    )


@router.get("/notifications", response_model=NotificationListOut)
async def list_notifications(
    user: User = Depends(require_role(*OWNER_ROLES)),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False),
) -> NotificationListOut:
    cond = _visible_filter(user)
    q = select(Notification).where(cond)
    if unread_only:
        q = q.where(Notification.is_read.is_(False))
    q = q.order_by(Notification.created_at.desc()).limit(limit)
    rows = (await session.execute(q)).scalars().all()

    unread = (
        await session.execute(
            select(func.count())
            .select_from(Notification)
            .where(cond, Notification.is_read.is_(False))
        )
    ).scalar_one()

    return NotificationListOut(
        unread_count=int(unread),
        items=[
            NotificationOut(
                id=n.id,
                severity=n.severity,
                category=n.category,
                title=n.title,
                body=n.body,
                financial_impact=float(n.financial_impact) if n.financial_impact is not None else None,
                link=n.link,
                ref_type=n.ref_type,
                ref_id=n.ref_id,
                is_read=n.is_read,
                created_at=n.created_at,
            )
            for n in rows
        ],
    )


@router.post("/notifications/{notif_id}/read", response_model=MarkReadResponse)
async def mark_read(
    notif_id: uuid.UUID,
    user: User = Depends(require_role(*OWNER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> MarkReadResponse:
    n = (
        await session.execute(select(Notification).where(Notification.id == notif_id))
    ).scalar_one_or_none()
    if n is None or n.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="التنبيه غير موجود")
    if n.user_id not in (None, user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="ليس لديك صلاحية")
    n.is_read = True
    await session.commit()
    return MarkReadResponse(updated=1)


@router.post("/notifications/read-all", response_model=MarkReadResponse)
async def mark_all_read(
    user: User = Depends(require_role(*OWNER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> MarkReadResponse:
    res = await session.execute(
        update(Notification)
        .where(_visible_filter(user), Notification.is_read.is_(False))
        .values(is_read=True)
    )
    await session.commit()
    return MarkReadResponse(updated=res.rowcount or 0)


@router.get("/daily-digests", response_model=list[DailyDigestOut])
async def daily_digests(
    user: User = Depends(require_role(*OWNER_ROLES)),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(30, ge=1, le=120),
) -> list[DailyDigestOut]:
    rows = (
        await session.execute(
            select(DailyDigest)
            .where(DailyDigest.company_id == user.company_id)
            .order_by(DailyDigest.digest_date.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        DailyDigestOut(
            id=d.id,
            digest_date=d.digest_date,
            waste_total_iqd=float(d.waste_total_iqd),
            tasks_completed=d.tasks_completed,
            tasks_overdue=d.tasks_overdue,
            alerts_open=d.alerts_open,
            trust_index=d.trust_index,
            message=d.message,
            whatsapp_sent=d.whatsapp_sent,
            created_at=d.created_at,
        )
        for d in rows
    ]
