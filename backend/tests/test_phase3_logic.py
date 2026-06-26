import os, sys, uuid
import os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.update({"SUPABASE_DB_HOST":"x","SUPABASE_DB_USER":"x","SUPABASE_DB_PASSWORD":"x",
 "SECRET_KEY":"x","JWT_SECRET":"x","ENCRYPTION_MASTER_KEY":"k"})

from app.ocr import parse_fields, flag_for_confidence, build_extracted_data
from app.ledger import compute_hash, verify_chain, GENESIS_HASH

P=[];F=[]
def ck(n,c): (P if c else F).append(n); print(("PASS " if c else "FAIL ")+n)

# --- confidence flagging ---
ck("flag green >=85", flag_for_confidence(90,"x")=="green")
ck("flag yellow 60-84", flag_for_confidence(70,"x")=="yellow")
ck("flag red <60", flag_for_confidence(40,"x")=="red")
ck("flag red missing value", flag_for_confidence(99,None)=="red")
ck("flag red empty list", flag_for_confidence(99,[])=="red")

# --- field parsing (Arabic + Latin) ---
text = """فاتورة رقم: INV-2024-0098
التاريخ: 2024/03/15
المورد: شركة بغداد للتجارة
حاسوب محمول 1500000
طابعة ليزر 250000
المبلغ الإجمالي: 1750000
"""
f = parse_fields(text)
ck("parse invoice_number", f["invoice_number"]=="INV-2024-0098")
ck("parse date", f["date"]=="2024/03/15")
ck("parse amount", f["amount"]=="1750000")
ck("parse vendor", "بغداد" in (f["vendor_name"] or ""))
ck("parse items (>=2)", len(f["items_list"])>=2)

# arabic-digit amount normalization
f2 = parse_fields("المبلغ: ١٢٣٤٥")
ck("arabic digits normalized", f2["amount"]=="12345")

# --- extracted_data structure ---
conf = {"invoice_number":90,"date":70,"amount":90,"vendor_name":50,"items_list":90}
ed = build_extracted_data(f, conf, 84.0, raw_text=text)
ck("color_flags present for all fields", set(ed["color_flags"])=={"invoice_number","date","amount","vendor_name","items_list"})
ck("vendor flagged red (<60)", ed["color_flags"]["vendor_name"]=="red")
ck("date flagged yellow", ed["color_flags"]["date"]=="yellow")

# --- ledger hash chain ---
def mk(prev, rid, cb, nv):
    h = compute_hash(previous_hash=prev, table_name="document_certifications",
                     record_id=rid, action="insert", new_value=nv, old_value=None, created_by=cb)
    return {"previous_hash":prev,"current_hash":h,"table_name":"document_certifications",
            "record_id":rid,"action":"insert","new_value":nv,"old_value":None,"created_by":cb}
e1=mk(GENESIS_HASH,"r1","u1",{"a":1})
e2=mk(e1["current_hash"],"r2","u1",{"a":2})
e3=mk(e2["current_hash"],"r3","u2",{"a":3})
chain=[e1,e2,e3]
ck("valid chain verifies", verify_chain(chain) is True)
# tamper with middle entry's data
tampered=[dict(x) for x in chain]
tampered[1]=dict(tampered[1]); tampered[1]["new_value"]={"a":999}
ck("tampered chain fails", verify_chain(tampered) is False)
# break linkage
broken=[dict(x) for x in chain]; broken[2]=dict(broken[2]); broken[2]["previous_hash"]="deadbeef"
ck("broken linkage fails", verify_chain(broken) is False)

print(f"\n=== {len(P)} passed, {len(F)} failed ===")
sys.exit(1 if F else 0)
