import os, sys, os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.update({"SUPABASE_DB_HOST":"x","SUPABASE_DB_USER":"x","SUPABASE_DB_PASSWORD":"x",
 "SECRET_KEY":"x","ENCRYPTION_MASTER_KEY":"k","SUPABASE_URL":"https://x.supabase.co"})
from app.services import criteria_library as cl
from app.services.template_engine import render_pdf, DUMMY

P=[];F=[]
def ck(n,c): (P if c else F).append(n); print(("PASS " if c else "FAIL ")+n)

# criteria library
mods = cl.list_modules()
ck("4 sector modules", len(mods)==4)
ck("real_estate has occupancy_rate", any(any(m["key"]=="occupancy_rate" for m in mod["metrics"]) for mod in mods if mod["sector"]=="real_estate"))
ck("manufacturing has oee", any(m["key"]=="oee" for m in cl.get_module("manufacturing")["metrics"]))
flat = cl.metrics_for_sectors(["real_estate","trading"])
ck("metrics_for_sectors merges", any(m["key"]=="rental_yield" for m in flat) and any(m["key"]=="margin" for m in flat))
ck("unknown sector -> none", cl.get_module("space_mining") is None)

# template render -> PDF
config = {
  "title": "تقرير العقارات المخصص",
  "blocks": [
    {"type":"text","content":"ملخص الأداء الشهري"},
    {"type":"metric","binding":"occupancy_rate","label":"نسبة الإشغال"},
    {"type":"metric","binding":"trust_index","label":"مؤشر الثقة"},
    {"type":"table","source":"waste_map_items","columns":["department","category","amount_iqd","status"]},
    {"type":"chart","source":"waste_by_department"},
    {"type":"image","placeholder":"شعار الشركة"},
  ],
}
pdf = render_pdf(config, DUMMY, title="تقرير العقارات المخصص")
ck("template render -> PDF magic", pdf[:4]==b"%PDF")
ck("PDF non-trivial size (has chart+table)", len(pdf) > 8000)

# empty config still renders
pdf2 = render_pdf({"title":"فارغ","blocks":[]}, DUMMY)
ck("empty template renders", pdf2[:4]==b"%PDF")

print(f"\n=== {len(P)} passed, {len(F)} failed ===")
sys.exit(1 if F else 0)
