"""Arabic WhatsApp/notification message templates + DND + phone helpers."""
from __future__ import annotations

import re
from datetime import datetime

from app.config import settings
from app.services import sla


def fmt_iqd(amount: float | None) -> str:
    if amount is None:
        return "غير محدد"
    return f"{amount:,.0f}"


def critical_alert_msg(*, dept: str, short_desc: str, amount: float | None) -> str:
    return (
        "🚨 تنبيه حرج - AuditCore\n"
        f"القسم: {dept}\n"
        f"المشكلة: {short_desc}\n"
        f"التأثير المالي: {fmt_iqd(amount)} د.ع\n"
        "الإجراء: افتح لوحة التحكم فوراً"
    )


def daily_digest_msg(*, amount: float, completed: int, alerts: int, score: int | None) -> str:
    return (
        "📊 ملخص AuditCore اليومي\n"
        f"الهدر المحتمل: {fmt_iqd(amount)} د.ع\n"
        f"المهام المكتملة: {completed}\n"
        f"التنبيهات: {alerts}\n"
        f"مؤشر الثقة: {score if score is not None else 0}%"
    )


def task_overdue_msg(*, name: str, title: str, hours: float) -> str:
    return (
        "⏰ تأخر مهمة تدقيق\n"
        f"المدقق: {name}\n"
        f"المهمة: {title}\n"
        f"متأخرة بـ: {hours:.0f} ساعة"
    )


def is_dnd(now_bg: datetime | None = None) -> bool:
    """True if the current Baghdad time is within Do-Not-Disturb hours."""
    now_bg = now_bg or sla.now_baghdad()
    h = now_bg.hour
    start, end = settings.DND_START_HOUR, settings.DND_END_HOUR
    if start == end:
        return False
    if start < end:
        return start <= h < end
    # Wraps midnight (e.g. 23 -> 6).
    return h >= start or h < end


def normalize_phone(raw: str | None) -> str | None:
    """Normalize a phone to digits only with country code; None if unusable."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = settings.DEFAULT_COUNTRY_CODE + digits[1:]
    # If it looks local (no country code), prepend default.
    if len(digits) <= 10 and not digits.startswith(settings.DEFAULT_COUNTRY_CODE):
        digits = settings.DEFAULT_COUNTRY_CODE + digits
    return digits
