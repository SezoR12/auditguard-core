import os, sys, os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.update({"SUPABASE_DB_HOST":"x","SUPABASE_DB_USER":"x","SUPABASE_DB_PASSWORD":"x",
 "SECRET_KEY":"x","ENCRYPTION_MASTER_KEY":"k","SUPABASE_URL":"https://x.supabase.co"})
from app.ai.sector_metrics import (safe_eval_formula, collect_base_inputs,
    compute_sector_metrics, sectors_for_company)
from app.ai.common import record_from_document

P=[];F=[]
def ck(n,c): (P if c else F).append(n); print(("PASS " if c else "FAIL ")+n)

# --- safe evaluator ---
ck("basic arithmetic", safe_eval_formula("a + b * 2", {"a":1,"b":3})==7.0)
ck("division", safe_eval_formula("(revenue - cogs) / revenue * 100", {"revenue":1000,"cogs":600})==40.0)
ck("missing var -> None", safe_eval_formula("a / b", {"a":1}) is None)
ck("div by zero -> None", safe_eval_formula("a / b", {"a":1,"b":0}) is None)
ck("injection rejected (no calls)", safe_eval_formula("__import__('os').system('x')", {}) is None)
ck("attribute access rejected", safe_eval_formula("a.__class__", {"a":1}) is None)
ck("name not in vars rejected", safe_eval_formula("os", {}) is None)

# --- base input aggregation from docs (extra sector fields summed) ---
def doc(fields, ckey="report"):
    return {"id":"d","doc_category":"report","branch_id":None,
            "extracted_data":{"category_key":ckey,"fields":fields}}
recs = [
    record_from_document(doc({"invoice_number":"INV-1","amount":"100","occupied_units":"8","total_units":"10"})),
    record_from_document(doc({"invoice_number":"INV-2","amount":"200","occupied_units":"7","total_units":"10"})),
]
base = collect_base_inputs(recs)
ck("aggregates occupied_units (8+7=15)", base.get("occupied_units")==15.0)
ck("aggregates total_units (10+10=20)", base.get("total_units")==20.0)
ck("reserved 'amount' NOT a base var", "amount" not in base)

# --- full real-estate computation: occupancy = 15/20*100 = 75 ---
m = compute_sector_metrics(recs, ["real_estate"])
ck("occupancy_rate computed", m.get("occupancy_rate")==75.0)
# rental_yield needs annual_rent/property_value -> absent -> omitted
ck("rental_yield omitted (missing vars)", "rental_yield" not in m)

# --- trading: revenue/cogs ---
recs2=[record_from_document(doc({"revenue":"1000","cogs":"600","avg_inventory":"200"}))]
mt = compute_sector_metrics(recs2, ["trading"])
ck("margin = 40%", mt.get("margin")==40.0)
ck("inventory_turnover = 3 (600/200)", mt.get("inventory_turnover")==3.0)

# --- sector mapping ---
ck("arabic عقارات -> real_estate", sectors_for_company("عقارات")==["real_estate"])
ck("arabic تجارة -> trading", sectors_for_company("تجارة")==["trading"])
ck("english restaurant -> restaurants", sectors_for_company("Fine Restaurant")==["restaurants"])
ck("unknown -> []", sectors_for_company("بناء")==[])
ck("empty -> []", sectors_for_company(None)==[])

# --- no sectors -> empty metrics ---
ck("no sectors -> {}", compute_sector_metrics(recs, [])=={})

print(f"\n=== {len(P)} passed, {len(F)} failed ===")
sys.exit(1 if F else 0)
