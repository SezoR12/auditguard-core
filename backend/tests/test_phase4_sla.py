import os, sys
import os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.update({"SUPABASE_DB_HOST":"x","SUPABASE_DB_USER":"x","SUPABASE_DB_PASSWORD":"x",
 "SECRET_KEY":"x","JWT_SECRET":"x","ENCRYPTION_MASTER_KEY":"k"})
from datetime import datetime, timedelta, timezone
from app.services import sla

P=[];F=[]
def ck(n,c): (P if c else F).append(n); print(("PASS " if c else "FAIL ")+n)

# Baghdad tz
ck("Baghdad is UTC+3", sla.BAGHDAD_TZ.utcoffset(None)==timedelta(hours=3))

# SLA deadlines
g = datetime(2026,6,26,5,0,tzinfo=timezone.utc)
ck("OCR SLA 4h", sla.sla_deadline(g,"ocr_certification")==g+timedelta(hours=4))
ck("bank SLA 24h", sla.sla_deadline(g,"bank_statement")==g+timedelta(hours=24))
ck("reversal SLA 2h", sla.sla_deadline(g,"reversal")==g+timedelta(hours=2))
ck("custom SLA configurable", sla.sla_deadline(g,"custom",custom_hours=6)==g+timedelta(hours=6))
ck("unknown kind default 8h", sla.sla_deadline(g,"weird")==g+timedelta(hours=8))

# critical / demerit
ck("reversal is critical", sla.is_critical_kind("reversal") is True)
ck("ocr not critical", sla.is_critical_kind("ocr_certification") is False)
ck("critical demerit=3", sla.demerit_for(True)==3)
ck("normal demerit=1", sla.demerit_for(False)==1)

# seconds remaining
now = datetime(2026,6,26,6,0,tzinfo=timezone.utc)
ck("seconds remaining positive", sla.seconds_remaining(now+timedelta(hours=1), now)==3600)
ck("seconds remaining negative (overdue)", sla.seconds_remaining(now-timedelta(hours=1), now)==-3600)
ck("seconds remaining None deadline", sla.seconds_remaining(None, now) is None)

# time color: created at g (5:00), deadline 4h later (9:00)
created = g; deadline = g+timedelta(hours=4)
ck("color green early (>50% left)", sla.time_color(deadline, created, g+timedelta(hours=1))=="green")
ck("color yellow (<50% left)", sla.time_color(deadline, created, g+timedelta(hours=2,minutes=30))=="yellow")
ck("color red overdue", sla.time_color(deadline, created, g+timedelta(hours=5))=="red")

# efficiency = on_time/total*100 - demerits*5
ck("efficiency basic", sla.efficiency_score(8,10,0)==80.0)
ck("efficiency w/ demerits", sla.efficiency_score(8,10,2)==70.0)   # 80 - 10
ck("efficiency clamps to 0", sla.efficiency_score(0,10,5)==0.0)    # 0 - 25 -> 0
ck("efficiency clamps to 100", sla.efficiency_score(10,10,0)==100.0)
ck("efficiency zero tasks", sla.efficiency_score(0,0,0)==0.0)

print(f"\n=== {len(P)} passed, {len(F)} failed ===")
sys.exit(1 if F else 0)
