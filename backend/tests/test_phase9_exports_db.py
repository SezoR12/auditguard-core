import os, sys, os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import asyncio, uuid, time
from datetime import datetime, timezone, timedelta
from jose import jwt
import httpx
from httpx import ASGITransport
from app.database import AsyncSessionLocal, engine, set_user_role
from app.models import Company, Branch, User, AuditTask, WasteMapItem
from app.models.enums import CompanyTier, UserRole, TaskStatus, TaskType, WasteCategory
from app.config import settings
from app.main import app

P=[];F=[]
def ck(n,c): (P if c else F).append(n); print(("PASS " if c else "FAIL ")+n)
def mint(sub,email): return jwt.encode({"sub":sub,"email":email,"aud":"authenticated","iat":int(time.time()),"exp":int(time.time())+3600}, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

MGR=str(uuid.uuid4()); OWN=str(uuid.uuid4()); AUD2_AUTH=str(uuid.uuid4())

async def main():
    async with AsyncSessionLocal() as s:
        await set_user_role(s,"admin")
        c=Company(name="ش", sector="t", tier=CompanyTier.advanced); s.add(c); await s.flush()
        bA=Branch(company_id=c.id, name="فرع أ", location="بغداد"); bB=Branch(company_id=c.id, name="فرع ب", location="البصرة")
        s.add_all([bA,bB]); await s.flush()
        mgr=User(email="m@x.com", full_name="المدير", role=UserRole.manager, company_id=c.id, branch_id=bA.id, is_active=True, auth_user_id=uuid.UUID(MGR))
        owner=User(email="o@x.com", full_name="المالك", role=UserRole.owner, company_id=c.id, is_active=True, auth_user_id=uuid.UUID(OWN))
        audA=User(email="aa@x.com", full_name="مدقق أ", role=UserRole.auditor, company_id=c.id, branch_id=bA.id, is_active=True)
        audB=User(email="ab@x.com", full_name="مدقق ب", role=UserRole.auditor, company_id=c.id, branch_id=bB.id, is_active=True)
        s.add_all([mgr,owner,audA,audB]); await s.flush()
        # 2 open tasks in branch A, 3 in branch B
        now=datetime.now(timezone.utc)
        for i in range(2):
            s.add(AuditTask(auditor_id=audA.id, title=f"A{i}", task_type=TaskType.document_review, status=TaskStatus.pending, sla_deadline=now+timedelta(hours=4)))
        for i in range(3):
            s.add(AuditTask(auditor_id=audB.id, title=f"B{i}", task_type=TaskType.document_review, status=TaskStatus.pending, sla_deadline=now+timedelta(hours=4)))
        # waste items for export
        s.add(WasteMapItem(company_id=c.id, category=WasteCategory.financial, amount_iqd=1500000, department="المشتريات", description="دفع مكرر", status="open"))
        s.add(WasteMapItem(company_id=c.id, category=WasteCategory.operational, amount_iqd=900000, department="المخازن", description="نقص جرد", status="open"))
        await s.commit()
        cid=c.id; wid=(await s.execute(__import__("sqlalchemy").select(WasteMapItem.id))).scalars().first()

    transport=ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        mh={"Authorization":f"Bearer {mint(MGR,'m@x.com')}"}
        oh={"Authorization":f"Bearer {mint(OWN,'o@x.com')}"}

        # widget list
        r=await ac.get("/manager/widgets", headers=mh)
        ck("manager widgets 200", r.status_code==200 and len(r.json()["widgets"])==5)

        # KEY: manager open_tasks sees ONLY branch A (2), not B (3)
        r=await ac.get("/manager/widget/open_tasks", headers=mh)
        ck("manager open_tasks 200", r.status_code==200)
        if r.status_code==200:
            ck("manager sees only branch A tasks (2)", r.json()["open_tasks"]==2)

        # owner (no branch) sees company-wide = 5
        r=await ac.get("/manager/widget/open_tasks", headers=oh)
        ck("owner sees all tasks (5)", r.status_code==200 and r.json()["open_tasks"]==5)

        # team_performance + pending_corrections respond
        ck("dept_quality_index ok", (await ac.get("/manager/widget/dept_quality_index", headers=mh)).status_code==200)
        ck("pending_corrections ok", (await ac.get("/manager/widget/pending_corrections", headers=mh)).status_code==200)

        # What-If with a real waste item
        r=await ac.post("/owner/what-if", headers=oh, json={"waste_item_id":str(wid),"recovery_pct":50,"implementation_months":3,"implementation_cost_iqd":150000,"horizon_months":6})
        ck("what-if 200", r.status_code==200)
        if r.status_code==200:
            ck("what-if recovered=750000 (50% of 1.5M)", r.json()["recovered_amount"]==750000)

        # Export Excel -> download via signed URL
        r=await ac.post("/owner/exports", headers=oh, json={"output_type":"waste_map","format":"excel"})
        ck("export create 200", r.status_code==200)
        if r.status_code==200:
            url=r.json()["download_url"]
            dl=await ac.get(url)  # no auth header — token authorizes
            ck("download via signed token 200", dl.status_code==200)
            ck("downloaded xlsx (PK magic)", dl.content[:2]==b"PK")
            ck("content-disposition attachment", "attachment" in dl.headers.get("content-disposition",""))

        # Export PDF + PNG
        rp=await ac.post("/owner/exports", headers=oh, json={"output_type":"waste_map","format":"pdf"})
        ck("export pdf 200", rp.status_code==200)
        rn=await ac.post("/owner/exports", headers=oh, json={"output_type":"waste_map","format":"png"})
        ck("export png 200", rn.status_code==200)

        # RLS / RBAC: auditor blocked
        ah={"Authorization":f"Bearer {mint(AUD2_AUTH,'aa@x.com')}"}
        ck("auditor manager widget 403", (await ac.get("/manager/widget/open_tasks", headers=ah)).status_code==403)
        ck("auditor exports 403", (await ac.post("/owner/exports", headers=ah, json={"output_type":"waste_map","format":"excel"})).status_code==403)
        ck("auditor what-if 403", (await ac.post("/owner/what-if", headers=ah, json={"base_amount_iqd":1000})).status_code==403)

    await engine.dispose()
    print(f"\n=== {len(P)} passed, {len(F)} failed ===")
    return 1 if F else 0
import sys; sys.exit(asyncio.run(main()))
