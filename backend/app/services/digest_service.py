"""Daily digest generator — one digest per owner, sent 07:00 Baghdad."""
from __future__ import annotations

import uuid
from datetime import timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AnalyticsOutput,
    AuditTask,
    Company,
    DailyDigest,
    Notification,
    RiskAlert,
    User,
    WasteMapItem,
)
from app.models.enums import OutputType, TaskStatus, UserRole
from app.services import notify_templates as tmpl
from app.services import sla, whatsapp


async def _yesterday_bounds_utc(now_bg):
    """[start, end) of yesterday's Baghdad day, in UTC."""
    today_start_bg = now_bg.replace(hour=0, minute=0, second=0, microsecond=0)
    y_start_bg = today_start_bg - timedelta(days=1)
    return y_start_bg.astimezone(timezone.utc), today_start_bg.astimezone(timezone.utc)


async def build_digest_for_company(session: AsyncSession, company: Company, now_bg) -> dict:
    cid = company.id
    y_start, y_end = await _yesterday_bounds_utc(now_bg)

    waste_total = (
        await session.execute(
            select(func.coalesce(func.sum(WasteMapItem.amount_iqd), 0)).where(
                WasteMapItem.company_id == cid,
                WasteMapItem.created_at >= y_start,
                WasteMapItem.created_at < y_end,
            )
        )
    ).scalar_one()

    completed = (
        await session.execute(
            select(func.count()).select_from(AuditTask).join(User, User.id == AuditTask.auditor_id).where(
                User.company_id == cid,
                AuditTask.status == TaskStatus.completed,
                AuditTask.completed_at >= y_start,
                AuditTask.completed_at < y_end,
            )
        )
    ).scalar_one()

    overdue = (
        await session.execute(
            select(func.count()).select_from(AuditTask).join(User, User.id == AuditTask.auditor_id).where(
                User.company_id == cid,
                AuditTask.status == TaskStatus.overdue,
            )
        )
    ).scalar_one()

    alerts_open = (
        await session.execute(
            select(func.count()).select_from(RiskAlert).where(
                RiskAlert.company_id == cid, RiskAlert.status == "open"
            )
        )
    ).scalar_one()

    trust = (
        await session.execute(
            select(AnalyticsOutput.trust_index)
            .where(
                AnalyticsOutput.company_id == cid,
                AnalyticsOutput.output_type == OutputType.daily_snapshot,
                AnalyticsOutput.trust_index.is_not(None),
            )
            .order_by(AnalyticsOutput.generated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    return {
        "waste_total": float(waste_total or 0),
        "completed": int(completed),
        "overdue": int(overdue),
        "alerts_open": int(alerts_open),
        "trust": int(trust) if trust is not None else None,
    }


async def generate_and_send_digests(session: AsyncSession) -> dict:
    """Build + persist + WhatsApp a digest for every owner. Idempotent per day."""
    now_bg = sla.now_baghdad()
    today = now_bg.date()

    companies = (await session.execute(select(Company))).scalars().all()
    total_sent = 0
    total_digests = 0

    for company in companies:
        metrics = await build_digest_for_company(session, company, now_bg)
        message = tmpl.daily_digest_msg(
            amount=metrics["waste_total"],
            completed=metrics["completed"],
            alerts=metrics["alerts_open"],
            score=metrics["trust"],
        )

        owners = (
            await session.execute(
                select(User).where(
                    User.company_id == company.id,
                    User.role.in_([UserRole.owner, UserRole.gm]),
                    User.is_active.is_(True),
                )
            )
        ).scalars().all()

        for owner in owners:
            # Idempotent: skip if a digest already exists for owner+date.
            existing = (
                await session.execute(
                    select(DailyDigest).where(
                        DailyDigest.owner_id == owner.id, DailyDigest.digest_date == today
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue

            sent = False
            phone = tmpl.normalize_phone(owner.whatsapp_phone)
            if phone and not tmpl.is_dnd(now_bg):
                res = await whatsapp.send_whatsapp(phone, message)
                sent = bool(res.get("sent"))

            session.add(
                DailyDigest(
                    company_id=company.id,
                    owner_id=owner.id,
                    digest_date=today,
                    waste_total_iqd=metrics["waste_total"],
                    tasks_completed=metrics["completed"],
                    tasks_overdue=metrics["overdue"],
                    alerts_open=metrics["alerts_open"],
                    trust_index=metrics["trust"],
                    message=message,
                    whatsapp_sent=sent,
                )
            )
            # Also drop an in-app notification of the digest.
            session.add(
                Notification(
                    company_id=company.id,
                    user_id=owner.id,
                    severity="low",
                    category="digest",
                    title="ملخص AuditCore اليومي",
                    body=message,
                    link={"layer": "owner"},
                )
            )
            total_digests += 1
            total_sent += 1 if sent else 0

    await session.commit()
    return {"digests": total_digests, "whatsapp_sent": total_sent}
