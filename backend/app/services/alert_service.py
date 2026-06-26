"""Alert classification + routing.

Severity routing:
  critical -> in-app notification + immediate WhatsApp (unless DND)
  high     -> in-app notification + bundled into daily digest (no instant WA)
  low/med  -> in-app notification only

Recipients: owners + GMs of the company (auditors are never recipients).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, User
from app.models.enums import UserRole
from app.services import notify_templates as tmpl
from app.services import whatsapp

# Roles that receive owner-level alerts.
RECIPIENT_ROLES = (UserRole.owner, UserRole.gm)


async def _recipients(session: AsyncSession, company_id: uuid.UUID) -> list[User]:
    rows = (
        await session.execute(
            select(User).where(
                User.company_id == company_id,
                User.role.in_(RECIPIENT_ROLES),
                User.is_active.is_(True),
            )
        )
    ).scalars().all()
    return list(rows)


async def create_notifications(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    severity: str,
    category: str,
    title: str,
    body: str,
    financial_impact: float | None = None,
    link: dict | None = None,
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
) -> list[Notification]:
    """Create one in-app notification per recipient (added, not committed)."""
    recipients = await _recipients(session, company_id)
    notifs: list[Notification] = []
    # If no explicit owner/gm exists, still record a broadcast notification.
    targets: list[uuid.UUID | None] = [u.id for u in recipients] or [None]
    for uid in targets:
        n = Notification(
            company_id=company_id,
            user_id=uid,
            severity=severity,
            category=category,
            title=title,
            body=body,
            financial_impact=financial_impact,
            link=link,
            ref_type=ref_type,
            ref_id=ref_id,
        )
        session.add(n)
        notifs.append(n)
    return notifs


async def dispatch_whatsapp_to_recipients(
    session: AsyncSession, company_id: uuid.UUID, message: str
) -> dict:
    """Send a WhatsApp message to every recipient with a phone (respects DND)."""
    if tmpl.is_dnd():
        return {"sent": 0, "queued": 0, "skipped_dnd": True}
    recipients = await _recipients(session, company_id)
    sent = queued = 0
    for u in recipients:
        phone = tmpl.normalize_phone(u.whatsapp_phone)
        if not phone:
            continue
        res = await whatsapp.send_whatsapp(phone, message)
        sent += 1 if res.get("sent") else 0
        queued += 1 if res.get("queued") else 0
    return {"sent": sent, "queued": queued, "skipped_dnd": False}


async def handle_risk_alert(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    severity: str,
    department: str,
    short_desc: str,
    financial_impact: float | None,
    ref_id: uuid.UUID | None = None,
    link: dict | None = None,
) -> dict:
    """Route a single risk alert per its severity. Commits nothing (caller does)."""
    notifs = await create_notifications(
        session,
        company_id=company_id,
        severity=severity,
        category="risk_alert",
        title=short_desc[:255],
        body=f"القسم: {department} — {short_desc}",
        financial_impact=financial_impact,
        link=link or {"layer": "analytics"},
        ref_type="risk_alert",
        ref_id=ref_id,
    )
    result = {"notifications": len(notifs), "whatsapp": None}
    if severity == "critical":
        msg = tmpl.critical_alert_msg(dept=department, short_desc=short_desc, amount=financial_impact)
        wa = await dispatch_whatsapp_to_recipients(session, company_id, msg)
        for n in notifs:
            n.whatsapp_sent = bool(wa.get("sent"))
        result["whatsapp"] = wa
    # high -> notification only here; included in the daily digest separately.
    return result


async def handle_task_overdue(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    auditor_name: str,
    task_title: str,
    hours_overdue: float,
    ref_id: uuid.UUID | None = None,
) -> dict:
    """Notify owners/GM that an auditor task is overdue (high severity)."""
    notifs = await create_notifications(
        session,
        company_id=company_id,
        severity="high",
        category="task_overdue",
        title=f"تأخر مهمة: {task_title}"[:255],
        body=f"المدقق {auditor_name} تأخر في «{task_title}» بـ {hours_overdue:.0f} ساعة.",
        link={"layer": "performance"},
        ref_type="audit_task",
        ref_id=ref_id,
    )
    # High severity: in-app + WhatsApp (overdue is time-sensitive for owner).
    msg = tmpl.task_overdue_msg(name=auditor_name, title=task_title, hours=hours_overdue)
    wa = await dispatch_whatsapp_to_recipients(session, company_id, msg)
    for n in notifs:
        n.whatsapp_sent = bool(wa.get("sent"))
    return {"notifications": len(notifs), "whatsapp": wa}
