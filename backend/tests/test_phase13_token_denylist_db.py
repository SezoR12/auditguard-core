import os, sys, os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import asyncio, uuid, time
from jose import jwt
import httpx
from httpx import ASGITransport
from app.database import AsyncSessionLocal, set_user_role
from app.models import Company, User
from app.models.enums import CompanyTier, UserRole
from app.config import settings
from app.services import token_denylist
from app.main import app

P=[];F=[]
def ck(n,c): (P if c else F).append(n); print(("PASS " if c else "FAIL ")+n)
def mint(sub,email,iat=None,exp=None):
    now=int(time.time())
    return jwt.encode({"sub":sub,"email":email,"aud":"authenticated","iat":iat or now,"exp":exp or now+3600},
                      settings.SUPABASE_JWT_SECRET, algorithm="HS256")

async def main():
    sub=str(uuid.uuid4()); email=f"d{uuid.uuid4().hex[:8]}@x.com"
    async with AsyncSessionLocal() as s:
        await set_user_role(s,"admin")
        c=Company(name="ش", sector="t", tier=CompanyTier.advanced); s.add(c); await s.flush()
        s.add(User(email=email, full_name="U", role=UserRole.owner, company_id=c.id, is_active=True, auth_user_id=uuid.UUID(sub)))
        await s.commit()
    tok=mint(sub,email)
    t=ASGITransport(app=app)
    async with httpx.AsyncClient(transport=t, base_url="http://t") as ac:
        # valid first
        r=await ac.get("/auth/me", headers={"Authorization":f"Bearer {tok}"})
        ck("valid token -> 200", r.status_code==200)
        # logout revokes THIS token
        r=await ac.post("/auth/logout", headers={"Authorization":f"Bearer {tok}"})
        ck("logout revoked=true", r.status_code==200 and r.json()["revoked"] is True)
        r=await ac.get("/auth/me", headers={"Authorization":f"Bearer {tok}"})
        ck("revoked token -> 401", r.status_code==401)
        # a NEW token still works
        tok2=mint(sub,email,iat=int(time.time())+1)
        r=await ac.get("/auth/me", headers={"Authorization":f"Bearer {tok2}"})
        ck("fresh token still 200", r.status_code==200)
        # revoke ALL user sessions -> tok2 (older iat) denied
        await token_denylist.revoke_user(sub, before=int(time.time())+3)
        await asyncio.sleep(1)
        r=await ac.get("/auth/me", headers={"Authorization":f"Bearer {tok2}"})
        ck("user-revoke kills existing token -> 401", r.status_code==401)
        # token issued AFTER the revoke cutoff works again
        tok3=mint(sub,email,iat=int(time.time())+10)
        r=await ac.get("/auth/me", headers={"Authorization":f"Bearer {tok3}"})
        ck("token issued after revoke -> 200", r.status_code==200)

        # ── Redis-outage behaviour (fail-open vs fail-closed) ────────────────
        # Simulate Redis being unreachable by making the client raise on use.
        class _Boom:
            def __getattr__(self, _):
                raise RuntimeError("redis down")
        orig_redis = token_denylist._redis
        orig_fc = settings.TOKEN_DENYLIST_FAIL_CLOSED
        token_denylist._redis = lambda: _Boom()
        tok4 = mint(sub, email, iat=int(time.time()) + 20)
        try:
            # Fail OPEN (default): request still succeeds despite Redis down.
            settings.TOKEN_DENYLIST_FAIL_CLOSED = False
            r = await ac.get("/auth/me", headers={"Authorization": f"Bearer {tok4}"})
            ck("redis down + fail-open -> 200", r.status_code == 200)
            # Fail CLOSED: request rejected with 503 (not 401).
            settings.TOKEN_DENYLIST_FAIL_CLOSED = True
            r = await ac.get("/auth/me", headers={"Authorization": f"Bearer {tok4}"})
            ck("redis down + fail-closed -> 503", r.status_code == 503)
            ck("fail-closed 503 detail is Arabic", "خدمة" in r.json().get("detail", ""))
        finally:
            token_denylist._redis = orig_redis
            settings.TOKEN_DENYLIST_FAIL_CLOSED = orig_fc

        # After Redis is restored, the token is accepted again.
        r = await ac.get("/auth/me", headers={"Authorization": f"Bearer {tok4}"})
        ck("redis restored -> 200", r.status_code == 200)
    print(f"\n=== {len(P)} passed, {len(F)} failed ===")
    return 1 if F else 0
import sys as _s; _s.exit(asyncio.run(main()))
