import os, sys, os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import asyncio, uuid, time
from jose import jwt
import httpx
from httpx import ASGITransport
from sqlalchemy import select
from app.database import AsyncSessionLocal, engine, set_user_role
from app.models import Company, Branch, User, Document
from app.models.enums import CompanyTier, UserRole, DocStatus, DocCategory, FileType
from app.ai.orchestrator import run_analysis_for_company
from app.config import settings
from app.main import app

P=[];F=[]
def ck(n,c): (P if c else F).append(n); print(("PASS " if c else "FAIL ")+n)
OWNER=str(uuid.uuid4()); AUD=str(uuid.uuid4())
def mint(sub,email): return jwt.encode({"sub":sub,"email":email,"aud":"authenticated","role":"authenticated","iat":int(time.time()),"exp":int(time.time())+3600}, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

def doc(cid, num, amt, vendor, cat=DocCategory.invoice, ckey="invoice", items=None, uploader=None):
    return Document(file_path="p", original_filename=f"{num}.jpg", file_type=FileType.image,
        doc_category=cat, status=DocStatus.certified, uploaded_by=uploader, company_id=cid,
        extracted_data={"category_key":ckey,"fields":{"invoice_number":num,"date":"2024/01/15",
            "amount":str(amt),"vendor_name":vendor,"items_list":items or []}})

async def main():
    async with AsyncSessionLocal() as s:
        await set_user_role(s,"admin")
        c=Company(name="ش", sector="t", tier=CompanyTier.advanced); s.add(c); await s.flush()
        b=Branch(company_id=c.id, name="الرئيسي", location="بغداد"); s.add(b); await s.flush()
        owner=User(email="o@x.com", full_name="المالك", role=UserRole.owner, company_id=c.id, is_active=True, auth_user_id=uuid.UUID(OWNER))
        aud=User(email="a@x.com", full_name="مدقق", role=UserRole.auditor, company_id=c.id, branch_id=b.id, is_active=True, auth_user_id=uuid.UUID(AUD))
        s.add_all([owner,aud]); await s.flush()
        docs=[doc(c.id, f"INV-{100+i}", 500000+i*9000, "المورد أ", uploader=aud.id) for i in range(12)]
        docs.append(doc(c.id,"INV-100",500000,"المورد أ", uploader=aud.id))  # duplicate
        docs.append(doc(c.id,"BANK-1",1200000,"البنك",cat=DocCategory.statement,ckey="bank_statement", uploader=aud.id))
        docs.append(doc(c.id,"INVREP-1",0,"المخزن",cat=DocCategory.report,ckey="inventory_report",items=[{"description":"شاشة","value":"99"}], uploader=aud.id))
        s.add_all(docs); await s.commit()
        cid=c.id; first_doc=docs[0].id
    # populate dashboard tables
    res=await run_analysis_for_company(cid)
    print("   analysis:", {k:res[k] for k in ("waste_items","cross_ref_findings","trust_index","anomalies")})

    transport=ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
        oh={"Authorization":f"Bearer {mint(OWNER,'o@x.com')}"}
        ah={"Authorization":f"Bearer {mint(AUD,'a@x.com')}"}
        # Layer 1
        r=await ac.get("/owner/dashboard/layer1", headers=oh)
        ck("L1 owner 200", r.status_code==200)
        if r.status_code==200:
            cards={c['key']:c for c in r.json()['cards']}
            ck("L1 has 5 cards", len(r.json()['cards'])==5)
            ck("L1 keys", set(cards)=={"monthly_waste","trust_index","critical_alerts","predicted_cash","team_efficiency"})
            ck("L1 trust_index populated", cards['trust_index']['value']>0)
            print("   L1 waste:",cards['monthly_waste']['value'],"trust:",cards['trust_index']['value'])
        # Layer 2
        r=await ac.get("/owner/dashboard/layer2", headers=oh)
        ck("L2 owner 200", r.status_code==200)
        if r.status_code==200:
            ck("L2 departments present", len(r.json()['departments'])>0)
            ck("L2 categories present", len(r.json()['categories'])>0)
        # Layer 3
        r=await ac.get("/owner/dashboard/layer3", headers=oh)
        ck("L3 owner 200", r.status_code==200)
        if r.status_code==200:
            d=r.json()
            ck("L3 narratives present", len(d['narratives'])>0)
            ck("L3 cross-ref present", len(d['cross_reference_findings'])>0)
        # Layer 4
        r=await ac.get(f"/owner/dashboard/layer4/{first_doc}", headers=oh)
        ck("L4 owner 200", r.status_code==200)
        if r.status_code==200:
            d=r.json()
            ck("L4 has image (decrypted)", d['original_image_url'] is not None)
            ck("L4 has extracted_data", d['extracted_data'] is not None)
            ck("L4 uploader name", d['uploaded_by_name']=="مدقق")
        # RLS: auditor -> 403 on all layers
        for path in ["/owner/dashboard/layer1","/owner/dashboard/layer2","/owner/dashboard/layer3",f"/owner/dashboard/layer4/{first_doc}"]:
            r=await ac.get(path, headers=ah)
            ck(f"auditor 403 on {path.split('/')[-1][:6]}", r.status_code==403)
    await engine.dispose()
    print(f"\n=== {len(P)} passed, {len(F)} failed ===")
    return 1 if F else 0
import sys; sys.exit(asyncio.run(main()))
