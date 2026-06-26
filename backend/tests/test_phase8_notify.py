import os, sys, os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.update({"SUPABASE_DB_HOST":"x","SUPABASE_DB_USER":"x","SUPABASE_DB_PASSWORD":"x",
 "SECRET_KEY":"x","ENCRYPTION_MASTER_KEY":"k","SUPABASE_URL":"https://x.supabase.co"})
from datetime import datetime, timezone, timedelta
from app.services import notify_templates as t
from app.config import settings

P=[];F=[]
def ck(n,c): (P if c else F).append(n); print(("PASS " if c else "FAIL ")+n)

# templates
m=t.critical_alert_msg(dept="المشتريات", short_desc="فاتورة مكررة", amount=1500000)
ck("critical template has marker", "تنبيه حرج" in m and "1,500,000" in m and "المشتريات" in m)
d=t.daily_digest_msg(amount=2000000, completed=5, alerts=3, score=88)
ck("digest template", "ملخص AuditCore" in d and "88%" in d and "2,000,000" in d)
o=t.task_overdue_msg(name="علي", title="جرد", hours=5)
ck("overdue template", "تأخر مهمة" in o and "علي" in o and "5 ساعة" in o)

# DND: default 23-06
bg=lambda h: datetime(2026,6,26,h,0,tzinfo=t.sla.BAGHDAD_TZ)
ck("DND at 02:00 = true", t.is_dnd(bg(2)) is True)
ck("DND at 12:00 = false", t.is_dnd(bg(12)) is False)
ck("DND at 23:00 = true", t.is_dnd(bg(23)) is True)
ck("DND at 06:00 = false (end exclusive)", t.is_dnd(bg(6)) is False)
ck("DND at 05:59 ~ true", t.is_dnd(bg(5)) is True)

# phone normalization (Iraq 964)
ck("local 0770... -> 964770...", t.normalize_phone("07701234567")=="9647701234567")
ck("already 964...", t.normalize_phone("9647701234567")=="9647701234567")
ck("+964 with plus", t.normalize_phone("+964 770 123 4567")=="9647701234567")
ck("00964 intl prefix", t.normalize_phone("00964770123")=="964770123")
ck("empty -> None", t.normalize_phone("") is None)

print(f"\n=== {len(P)} passed, {len(F)} failed ===")
sys.exit(1 if F else 0)
