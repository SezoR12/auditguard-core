import os, sys, os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import asyncio, uuid
from sqlalchemy import select
from app.database import AsyncSessionLocal, engine, set_user_role
from app.models import Company, User, Document, AnalyticsOutput
from app.models.enums import CompanyTier, UserRole, DocStatus, DocCategory, FileType, OutputType
from app.ai.orchestrator import run_analysis_for_company
from app.services.template_engine import resolve_data, render_pdf

P=[];F=[]
def ck(n,c): (P if c else F).append(n); print(("PASS " if c else "FAIL ")+n)

def rdoc(cid, up, num, extra):
    f={"invoice_number":num,"date":"2024/03/15","amount":"100000","vendor_name":"V","items_list":[]}
    f.update(extra)
    return Document(file_path="p", original_filename=f"{num}.jpg", file_type=FileType.image,
        doc_category=DocCategory.report, status=DocStatus.certified, company_id=cid, uploaded_by=up,
        extracted_data={"category_key":"inventory_report","fields":f})

async def main():
    async with AsyncSessionLocal() as s:
        await set_user_role(s,"admin")
        c=Company(name="شركة عقارية", sector="عقارات", tier=CompanyTier.elite); s.add(c); await s.flush()
        u=User(email=f"u{uuid.uuid4().hex[:6]}@x.com", full_name="u", role=UserRole.auditor, company_id=c.id, is_active=True); s.add(u); await s.flush()
        s.add(rdoc(c.id,u.id,"R1",{"occupied_units":"45","total_units":"50","annual_rent":"120000000","property_value":"1500000000"}))
        s.add(rdoc(c.id,u.id,"R2",{"occupied_units":"40","total_units":"50"}))
        await s.commit(); cid=c.id

    res=await run_analysis_for_company(cid)
    print("   sector_metrics:", res.get("sector_metrics"))
    ck("analysis ok", res.get("ok") is True)
    ck("occupancy_rate = 85.0", res["sector_metrics"].get("occupancy_rate")==85.0)
    ck("rental_yield = 8.0", res["sector_metrics"].get("rental_yield")==8.0)
    ck("vacancy_rate omitted", "vacancy_rate" not in res["sector_metrics"])

    async with AsyncSessionLocal() as s:
        await set_user_role(s,"admin")
        snap=(await s.execute(select(AnalyticsOutput).where(
            AnalyticsOutput.company_id==cid, AnalyticsOutput.output_type==OutputType.daily_snapshot
        ).order_by(AnalyticsOutput.generated_at.desc()).limit(1))).scalar_one()
        ck("snapshot stores sector_metrics", snap.data.get("sector_metrics",{}).get("occupancy_rate")==85.0)
        data=await resolve_data(s, cid, ["real_estate"])
        ck("resolve_data exposes occupancy", data["metrics"].get("occupancy_rate")==85.0)
        cfg={"title":"تقرير العقارات","blocks":[{"type":"metric","binding":"occupancy_rate","label":"نسبة الإشغال"}]}
        pdf=render_pdf(cfg, data, title="تقرير العقارات")
        ck("custom report PDF renders", pdf[:4]==b"%PDF" and len(pdf)>1500)

    await engine.dispose()
    print(f"\n=== {len(P)} passed, {len(F)} failed ===")
    return 1 if F else 0
import sys; sys.exit(asyncio.run(main()))
