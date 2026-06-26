import os, sys, os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import uuid as _uuid_sfx
_EMAIL_SFX = _uuid_sfx.uuid4().hex[:8]
def _em(addr):
    user, _, dom = addr.partition('@')
    return f'{user}+{_EMAIL_SFX}@{dom}'
import asyncio, uuid, time
from jose import jwt
import httpx
from httpx import ASGITransport
from sqlalchemy import select, func
from app.database import AsyncSessionLocal, engine, set_user_role
from app.models import Company, Branch, User, WasteMapItem, AnalyticsOutput, CustomReport, ReportRequest
from app.models.enums import CompanyTier, UserRole, WasteCategory, OutputType
from app.config import settings
from app.main import app

P=[];F=[]
def ck(n,c): (P if c else F).append(n); print(("PASS " if c else "FAIL ")+n)
APP=str(uuid.uuid4()); OWN=str(uuid.uuid4()); AUD=str(uuid.uuid4())
def mint(sub,email): return jwt.encode({"sub":sub,"email":email,"aud":"authenticated","iat":int(time.time()),"exp":int(time.time())+3600}, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

async def main():
    async with AsyncSessionLocal() as s:
        await set_user_role(s,"admin")
        c=Company(name="شركة عقارية", sector="عقارات", tier=CompanyTier.elite); s.add(c); await s.flush()
        b=Branch(company_id=c.id, name="الرئيسي", location="بغداد"); s.add(b); await s.flush()
        appo=User(email=_em('app@x.com'), full_name="مالك التطبيق", role=UserRole.appowner, company_id=c.id, is_active=True, auth_user_id=uuid.UUID(APP))
        own=User(email=_em('o@x.com'), full_name="المالك", role=UserRole.owner, company_id=c.id, is_active=True, auth_user_id=uuid.UUID(OWN))
        aud=User(email=_em('a@x.com'), full_name="مدقق", role=UserRole.auditor, company_id=c.id, branch_id=b.id, is_active=True, auth_user_id=uuid.UUID(AUD))
        s.add_all([appo,own,aud]); await s.flush()
        # live data for the client's report
        s.add(WasteMapItem(company_id=c.id, category=WasteCategory.financial, amount_iqd=1500000, department="المشتريات", description="دفع مكرر", status="open"))
        s.add(WasteMapItem(company_id=c.id, category=WasteCategory.operational, amount_iqd=900000, department="المخازن", description="نقص", status="open"))
        s.add(AnalyticsOutput(company_id=c.id, output_type=OutputType.daily_snapshot, trust_index=88,
              data={"total_waste_iqd":2400000,"sector_metrics":{"occupancy_rate":92,"rental_yield":7.5}}))
        await s.commit(); cid=c.id

    transport=ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        ah={"Authorization":f"Bearer {mint(APP,_em('app@x.com'))}"}
        oh={"Authorization":f"Bearer {mint(OWN,_em('o@x.com'))}"}
        adh={"Authorization":f"Bearer {mint(AUD,_em('a@x.com'))}"}

        # 1. App Owner sees criteria library
        r=await ac.get("/templates/criteria", headers=ah)
        ck("appowner criteria 200", r.status_code==200 and len(r.json()["modules"])==4)

        # 2. App Owner builds a template (no code — JSON config)
        cfg={"title":"تقرير العقارات","blocks":[
            {"type":"text","content":"ملخص"},
            {"type":"metric","binding":"occupancy_rate","label":"نسبة الإشغال"},
            {"type":"table","source":"waste_map_items","columns":["department","category","amount_iqd","status"]},
            {"type":"chart","source":"waste_by_department"}]}
        r=await ac.post("/templates", headers=ah, json={"name":"قالب العقارات","sectors":["real_estate"],"config":cfg,"is_published":True})
        ck("create template 201", r.status_code==201)
        tpl_id=r.json()["id"] if r.status_code==201 else None

        # preview with dummy data
        r=await ac.post(f"/templates/{tpl_id}/preview", headers=ah)
        ck("preview returns PDF", r.status_code==200 and r.content[:4]==b"%PDF")

        # 3. Client requests a custom report
        r=await ac.post("/owner/report-requests", headers=oh, json={"title":"تقرير إشغال شهري","requirements":"حسب الفرع"})
        ck("client request 201", r.status_code==201)
        req_id=r.json()["id"]

        # 4. App Owner sees the request in inbox, deploys the template
        r=await ac.get("/admin/report-requests", headers=ah)
        ck("appowner sees request", r.status_code==200 and any(x["id"]==req_id for x in r.json()))
        r=await ac.post(f"/admin/report-requests/{req_id}/deploy", headers=ah, json={"template_id":tpl_id,"price_iqd":250000,"report_name":"تقرير الإشغال"})
        ck("deploy 200", r.status_code==200 and r.json()["deployed"] is True)

        # 5. Report appears in CLIENT's custom-reports library
        r=await ac.get("/owner/custom-reports", headers=oh)
        ck("client sees deployed report", r.status_code==200 and len(r.json())==1)
        cr_id=r.json()[0]["id"] if r.json() else None

        # 6. Client generates PDF with LIVE data
        r=await ac.post(f"/owner/custom-reports/{cr_id}/generate", headers=oh)
        ck("client generates PDF", r.status_code==200 and r.content[:4]==b"%PDF")
        ck("generated PDF has content", len(r.content) > 8000)

        # 7. RBAC/RLS: auditor blocked + request status updated
        ck("auditor cannot list templates 403", (await ac.get("/templates", headers=adh)).status_code==403)
        ck("auditor cannot see custom-reports 403", (await ac.get("/owner/custom-reports", headers=adh)).status_code==403)
        ck("auditor cannot request 403", (await ac.post("/owner/report-requests", headers=adh, json={"title":"x"})).status_code==403)

    # RLS at DB layer: auditor sees 0 custom_reports
    async with AsyncSessionLocal() as s:
        await set_user_role(s,"auditor")
        n=(await s.execute(select(func.count()).select_from(CustomReport))).scalar_one()
    ck("auditor sees 0 custom_reports (RLS)", n==0)

    await engine.dispose()
    print(f"\n=== {len(P)} passed, {len(F)} failed ===")
    return 1 if F else 0
import sys; sys.exit(asyncio.run(main()))
