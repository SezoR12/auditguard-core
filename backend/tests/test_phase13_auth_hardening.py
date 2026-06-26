import os, sys, os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SUPABASE_DB_HOST","x"); os.environ.setdefault("SUPABASE_DB_USER","x")
os.environ.setdefault("SUPABASE_DB_PASSWORD","x"); os.environ.setdefault("SECRET_KEY","x")
os.environ.setdefault("ENCRYPTION_MASTER_KEY","k"); os.environ.setdefault("SUPABASE_URL","https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY","anonkey"); os.environ.setdefault("REDIS_URL","redis://localhost:6399/0")
import asyncio, uuid, httpx
from httpx import ASGITransport
import app.api.auth as authmod
from app.services import rate_limit
from app.main import app

P=[];F=[]
def ck(n,c): (P if c else F).append(n); print(("PASS " if c else "FAIL ")+n)

# Cleanly stub the upstream password grant (no global httpx mutation).
async def fake_grant(email, password):
    if password == "correct":
        return 200, {"access_token":"tok","refresh_token":"r","expires_in":3600}
    return 400, {"error":"invalid_grant"}
authmod._password_grant = fake_grant

async def main():
    email=f"u{uuid.uuid4().hex[:8]}@x.com"
    t=ASGITransport(app=app)
    async with httpx.AsyncClient(transport=t, base_url="http://t") as ac:
        last=None
        for _ in range(4):
            last=await ac.post("/auth/login", json={"email":email,"password":"wrong"})
        ck("4 bad attempts -> 401", last.status_code==401)
        ck("401 detail arabic", "غير صحيحة" in last.json().get("detail",""))
        r=await ac.post("/auth/login", json={"email":email,"password":"wrong"})
        ck("5th attempt -> 429 lockout", r.status_code==429)
        ck("429 retry-after header", "retry-after" in {k.lower() for k in r.headers})
        ck("429 arabic", "قفل" in r.json().get("detail",""))
        r=await ac.post("/auth/login", json={"email":email,"password":"correct"})
        ck("correct pw blocked during lockout", r.status_code==429)
        await rate_limit.clear(rate_limit.make_key(email, "127.0.0.1"))
        r=await ac.post("/auth/login", json={"email":email,"password":"correct"})
        ck("after clear, correct pw -> 200", r.status_code==200 and r.json()["access_token"]=="tok")
        email2=f"v{uuid.uuid4().hex[:8]}@x.com"
        await ac.post("/auth/login", json={"email":email2,"password":"wrong"})
        r=await ac.post("/auth/login", json={"email":email2,"password":"correct"})
        ck("success after a fail -> 200 tokens", r.status_code==200 and r.json()["access_token"]=="tok")
    print(f"\n=== {len(P)} passed, {len(F)} failed ===")
    return 1 if F else 0
import sys as _s; _s.exit(asyncio.run(main()))
