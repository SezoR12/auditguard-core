import os, sys, os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import asyncio, uuid, time
from jose import jwt
import httpx
from httpx import ASGITransport
from sqlalchemy import select, func
from app.database import AsyncSessionLocal, engine, set_user_role
from app.models import Company, Branch, User, Notification, DailyDigest, RiskAlert
from app.models.enums import CompanyTier, UserRole, Severity
from app.config import settings
from app.services import whatsapp, alert_service, digest_service
from app.main import app

P=[];F=[]
def ck(n,c): (P if c else F).append(n); print(("PASS " if c else "FAIL ")+n)
OWNER=str(uuid.uuid4()); AUD=str(uuid.uuid4())
def mint(sub,email): return jwt.encode({"sub":sub,"email":email,"aud":"authenticated","iat":int(time.time()),"exp":int(time.time())+3600}, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

# Control the "bridge": toggle online/offline + capture sent messages
SENT=[]
class Bridge:
    online=True
async def fake_post(to, message, timeout=8.0):
    if not Bridge.online:
        raise RuntimeError("bridge down")
    SENT.append((to, message)); return True
whatsapp._post_to_bridge = fake_post
# Force DND off for the test (simulate daytime)
import app.services.notify_templates as tmpl
tmpl.is_dnd = lambda now=None: False

async def main():
    async with AsyncSessionLocal() as s:
        await set_user_role(s,"admin")
        c=Company(name="ش", sector="t", tier=CompanyTier.advanced); s.add(c); await s.flush()
        b=Branch(company_id=c.id, name="الرئيسي", location="بغداد"); s.add(b); await s.flush()
        owner=User(email="o@x.com", full_name="المالك", role=UserRole.owner, company_id=c.id, is_active=True, auth_user_id=uuid.UUID(OWNER), whatsapp_phone="07701234567")
        aud=User(email="a@x.com", full_name="مدقق", role=UserRole.auditor, company_id=c.id, branch_id=b.id, is_active=True, auth_user_id=uuid.UUID(AUD))
        s.add_all([owner,aud]); await s.commit(); cid=c.id

    # 1. Critical alert -> notification + WhatsApp within the call
    async with AsyncSessionLocal() as s:
        await set_user_role(s,"admin")
        res=await alert_service.handle_risk_alert(s, company_id=cid, severity="critical",
            department="المشتريات", short_desc="دفع مكرر", financial_impact=1500000.0)
        await s.commit()
    ck("critical created notifications", res["notifications"]>=1)
    ck("critical WhatsApp sent immediately", res["whatsapp"] and res["whatsapp"]["sent"]>=1)
    ck("bridge received critical msg", any("تنبيه حرج" in m for _,m in SENT))

    # 2. Bridge offline -> queued in Redis -> flush sends when restored
    SENT.clear(); Bridge.online=False
    async with AsyncSessionLocal() as s:
        await set_user_role(s,"admin")
        await alert_service.handle_risk_alert(s, company_id=cid, severity="critical",
            department="المخازن", short_desc="نقص جرد", financial_impact=900000.0)
        await s.commit()
    import redis.asyncio as aioredis
    r=aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    qlen=await r.llen(settings.WHATSAPP_QUEUE_KEY)
    ck("offline -> queued in redis", qlen>=1)
    ck("nothing sent while offline", len(SENT)==0)
    # restore + flush
    Bridge.online=True
    flushed=await whatsapp.flush_queue()
    ck("flush sent queued msg", flushed["sent"]>=1)
    ck("bridge received after restore", any("نقص جرد" in m for _,m in SENT))
    qlen2=await r.llen(settings.WHATSAPP_QUEUE_KEY); await r.aclose()
    ck("queue drained", qlen2==0)

    # 3. low severity -> notification only, no WhatsApp
    SENT.clear()
    async with AsyncSessionLocal() as s:
        await set_user_role(s,"admin")
        res=await alert_service.handle_risk_alert(s, company_id=cid, severity="low",
            department="المبيعات", short_desc="ملاحظة", financial_impact=None)
        await s.commit()
    ck("low severity no whatsapp", res["whatsapp"] is None and len(SENT)==0)

    # 4. Daily digest
    SENT.clear()
    async with AsyncSessionLocal() as s:
        await set_user_role(s,"admin")
        dres=await digest_service.generate_and_send_digests(s)
    ck("digest created", dres["digests"]>=1)
    ck("digest whatsapp sent", dres["whatsapp_sent"]>=1)
    ck("bridge got digest msg", any("ملخص AuditCore" in m for _,m in SENT))

    # 5. Notification API: owner sees, auditor 403
    transport=ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        r=await ac.get("/owner/notifications", headers={"Authorization":f"Bearer {mint(OWNER,'o@x.com')}"})
        ck("owner notifications 200", r.status_code==200)
        if r.status_code==200:
            ck("owner has unread", r.json()["unread_count"]>=1)
            items=r.json()["items"]; ck("notifications listed", len(items)>=1)
            nid=items[0]["id"]
            rr=await ac.post(f"/owner/notifications/{nid}/read", headers={"Authorization":f"Bearer {mint(OWNER,'o@x.com')}"})
            ck("mark read 200", rr.status_code==200)
        r=await ac.get("/owner/daily-digests", headers={"Authorization":f"Bearer {mint(OWNER,'o@x.com')}"})
        ck("owner digests 200", r.status_code==200 and len(r.json())>=1)
        # auditor blocked
        ah={"Authorization":f"Bearer {mint(AUD,'a@x.com')}"}
        ck("auditor notifications 403", (await ac.get("/owner/notifications", headers=ah)).status_code==403)
        ck("auditor digests 403", (await ac.get("/owner/daily-digests", headers=ah)).status_code==403)
    # RLS at DB layer: auditor sees 0 notifications
    async with AsyncSessionLocal() as s:
        await set_user_role(s,"auditor")
        n=(await s.execute(select(func.count()).select_from(Notification))).scalar_one()
    ck("auditor sees 0 notifications (RLS)", n==0)

    await engine.dispose()
    print(f"\n=== {len(P)} passed, {len(F)} failed ===")
    return 1 if F else 0
import sys; sys.exit(asyncio.run(main()))
