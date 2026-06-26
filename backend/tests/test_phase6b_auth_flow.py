import os, sys, os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import uuid as _uuid_sfx
_EMAIL_SFX = _uuid_sfx.uuid4().hex[:8]
def _em(addr):
    user, _, dom = addr.partition('@')
    return f'{user}+{_EMAIL_SFX}@{dom}'
import asyncio, uuid, time
from datetime import datetime, timezone, timedelta
from jose import jwt
import httpx
from httpx import ASGITransport
from sqlalchemy import select
from app.database import AsyncSessionLocal, engine, set_user_role
from app.models import Company, Branch, User
from app.models.enums import CompanyTier, UserRole
from app.config import settings
from app.main import app

P=[];F=[]
def ck(n,c): (P if c else F).append(n); print(("PASS " if c else "FAIL ")+n)

OWNER_AUTH=str(uuid.uuid4()); AUD_AUTH=str(uuid.uuid4())

def mint(sub, email, secret=None, aud="authenticated", exp_delta=3600):
    payload={"sub":sub,"email":email,"role":"authenticated","aud":aud,
             "iat":int(time.time()),"exp":int(time.time())+exp_delta}
    return jwt.encode(payload, secret or settings.SUPABASE_JWT_SECRET, algorithm="HS256")

async def seed():
    async with AsyncSessionLocal() as s:
        await set_user_role(s,"admin")
        c=Company(name="ش الاختبار", sector="t", tier=CompanyTier.advanced); s.add(c); await s.flush()
        b=Branch(company_id=c.id, name="الرئيسي", location="بغداد"); s.add(b); await s.flush()
        s.add(User(email=_em("owner@auditcore.local"), full_name="المالك", role=UserRole.owner,
                   company_id=c.id, is_active=True, auth_user_id=uuid.UUID(OWNER_AUTH)))
        s.add(User(email=_em("auditor@auditcore.local"), full_name="المدقق", role=UserRole.auditor,
                   company_id=c.id, branch_id=b.id, is_active=True, auth_user_id=uuid.UUID(AUD_AUTH)))
        await s.commit()

async def main():
    await seed()
    transport=ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. no token -> 401
        r=await ac.get("/auth/me"); ck("no token -> 401", r.status_code==401)
        # 2. valid owner token -> /auth/me resolves profile
        tok=mint(OWNER_AUTH,_em("owner@auditcore.local"))
        r=await ac.get("/auth/me", headers={"Authorization":f"Bearer {tok}"})
        ck("owner /auth/me 200", r.status_code==200)
        if r.status_code==200:
            ck("owner role resolved", r.json().get("role")=="owner")
            ck("owner name resolved", "المالك" in r.json().get("full_name",""))
        # 3. owner can hit owner-gated endpoint
        r=await ac.get("/owner/dashboard", headers={"Authorization":f"Bearer {tok}"})
        ck("owner -> /owner/dashboard 200", r.status_code==200)
        # 4. auditor token -> blocked from owner endpoint (403, Arabic)
        atok=mint(AUD_AUTH,_em("auditor@auditcore.local"))
        r=await ac.get("/owner/dashboard", headers={"Authorization":f"Bearer {atok}"})
        ck("auditor -> /owner/dashboard 403", r.status_code==403)
        if r.status_code==403:
            ck("403 message arabic", "صلاحية" in r.json().get("detail",""))
        # 5. auditor can hit auditor endpoint
        r=await ac.get("/auditor/dashboard", headers={"Authorization":f"Bearer {atok}"})
        ck("auditor -> /auditor/dashboard 200", r.status_code==200)
        # 6. token signed with WRONG secret -> 401
        bad=mint(OWNER_AUTH,_em("owner@auditcore.local"), secret="wrong-secret")
        r=await ac.get("/auth/me", headers={"Authorization":f"Bearer {bad}"})
        ck("wrong-secret token -> 401", r.status_code==401)
        # 7. wrong audience -> 401
        wa=mint(OWNER_AUTH,_em("owner@auditcore.local"), aud="something-else")
        r=await ac.get("/auth/me", headers={"Authorization":f"Bearer {wa}"})
        ck("wrong audience -> 401", r.status_code==401)
        # 8. expired token -> 401
        ex=mint(OWNER_AUTH,_em("owner@auditcore.local"), exp_delta=-10)
        r=await ac.get("/auth/me", headers={"Authorization":f"Bearer {ex}"})
        ck("expired token -> 401", r.status_code==401)
        # 9. email-fallback linking: user with no auth_user_id gets linked by email
        async with AsyncSessionLocal() as s:
            await set_user_role(s,"admin")
            c=(await s.execute(select(Company))).scalars().first()
            s.add(User(email=_em("mgr@auditcore.local"), full_name="المدير", role=UserRole.manager,
                       company_id=c.id, is_active=True, auth_user_id=None))
            await s.commit()
        MGR_AUTH=str(uuid.uuid4())
        mtok=mint(MGR_AUTH,_em("mgr@auditcore.local"))
        r=await ac.get("/auth/me", headers={"Authorization":f"Bearer {mtok}"})
        ck("email-fallback links profile (200)", r.status_code==200)
        async with AsyncSessionLocal() as s:
            await set_user_role(s,"admin")
            u=(await s.execute(select(User).where(User.email==_em("mgr@auditcore.local")))).scalar_one()
            ck("auth_user_id backfilled via email", str(u.auth_user_id)==MGR_AUTH)

    await engine.dispose()
    print(f"\n=== {len(P)} passed, {len(F)} failed ===")
    return 1 if F else 0

import sys
sys.exit(asyncio.run(main()))
