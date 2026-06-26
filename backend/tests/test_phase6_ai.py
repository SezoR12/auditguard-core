import os, sys
import os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.update({"SUPABASE_DB_HOST":"x","SUPABASE_DB_USER":"x","SUPABASE_DB_PASSWORD":"x",
 "SECRET_KEY":"x","JWT_SECRET":"x","ENCRYPTION_MASTER_KEY":"k"})
from datetime import date
from app.ai.common import InvoiceRecord, record_from_document, to_float, parse_date
from app.ai import data_quality as dq, anomaly as an, cross_reference as xr, impact as imp
from app.ai import predictor as pr, narrative as nar, trust as tr

P=[];F=[]
def ck(n,c): (P if c else F).append(n); print(("PASS " if c else "FAIL ")+n)

# helpers
def rec(doc_id, num=None, dt=None, amt=None, vendor=None, cat="invoice", ck_key=None, items=None, branch=None):
    return InvoiceRecord(document_id=doc_id, category=cat, category_key=ck_key,
        invoice_number=num, invoice_seq=(int(''.join(filter(str.isdigit,num))) if num else None),
        txn_date=dt, amount=amt, vendor_name=vendor, items=items or [], branch_id=branch)

# --- common parsing ---
ck("to_float arabic digits", to_float("١٢٣٤")==1234.0)
ck("to_float commas", to_float("1,750,000")==1750000.0)
ck("parse_date YMD", parse_date("2024/03/15")==date(2024,3,15))
ck("parse_date DMY", parse_date("15-03-2024")==date(2024,3,15))
ck("record_from_document", record_from_document({"id":"d1","doc_category":"invoice",
    "extracted_data":{"fields":{"invoice_number":"INV-9","amount":"500","date":"2024/01/02","vendor_name":"V"}}}).amount==500.0)

# --- data quality: duplicate invoice ---
recs=[rec("d1","INV-100",date(2024,1,1),100,"المورد أ"),
      rec("d2","INV-100",date(2024,1,2),100,"المورد أ"),  # duplicate
      rec("d3",None,None,None,None)]  # missing all
flags=dq.run_data_quality(recs)
ck("duplicate invoice flagged", any(f.code=="duplicate_invoice_number" for f in flags))
ck("missing mandatory flagged", any(f.code=="missing_mandatory_fields" for f in flags))
ck("quality_score 0-100", 0<=dq.quality_score(recs,flags)<=100)

# --- anomaly: zscore needs 30+ ---
small=[rec(f"s{i}",f"A{i}",date(2024,1,1),100,"V") for i in range(10)]
ck("anomaly skipped below baseline", an.run_anomaly_detection(small)==[])
big=[rec(f"b{i}",f"A{i}",date(2024,1,1+i%27),100,"V") for i in range(40)]
big.append(rec("HUGE","A999",date(2024,1,1),100000,"V"))  # outlier
anoms=an.run_anomaly_detection(big)
ck("zscore outlier detected", any(a.code=="zscore_large_amount" for a in anoms))

# --- cross reference: procurement vs bank ---
recs2=[rec("p1","P1",date(2024,1,1),1000000,"V",cat="invoice"),
       rec("bk1","B1",date(2024,1,2),800000,"Bank",cat="statement",ck_key="bank_statement")]
xfind=xr.run_cross_reference(recs2)
ck("procurement vs bank variance flagged", any(f.finding_type=="procurement_vs_bank" for f in xfind))
ck("variance amount computed", any(f.variance_amount==200000 for f in xfind))

# --- cross reference: procurement vs inventory qty ---
recs3=[rec("p2","P2",date(2024,1,1),0,"V",cat="invoice",items=[{"description":"شاشة","value":"100"}]),
       rec("inv2","I2",date(2024,1,2),0,"W",cat="report",ck_key="inventory_report",items=[{"description":"شاشة","value":"80"}])]
xfind3=xr.run_cross_reference(recs3)
ck("procurement vs inventory qty variance", any(f.finding_type=="procurement_vs_inventory" for f in xfind3))

# --- impact: duplicate -> waste ---
rbi={r.document_id:r for r in recs}
waste=imp.run_impact(anoms, xfind, flags, rbi)
ck("impact produces waste items", len(waste)>0)
ck("waste has positive iqd", any(w.amount_iqd>0 for w in waste))
ck("duplicate payment waste present", any("مكرر" in w.description for w in waste))

# --- predictor ---
monthly=[rec(f"m{i}",f"M{i}",date(2024,(i%3)+1,15),100000*(i%3+1),"V") for i in range(9)]
preds=pr.run_predictions(monthly)
ck("prediction produced", len(preds)>=1)
ck("cash outflow predicted", any(p.metric=="next_month_cash_outflow" for p in preds))

# --- narrative ---
narrs=nar.run_narratives(waste, xfind, anoms, open_corrections=5)
ck("owner narrative present", any(n.audience=="owner" for n in narrs))
ck("manager narrative mentions corrections", any("5" in n.text for n in narrs if n.audience=="manager"))
ck("owner narrative arabic waste phrase", any("هدر" in n.text for n in narrs if n.audience=="owner"))

# --- trust index ---
ti=tr.trust_index(quality=90.0, coverage=1.0, anomaly_count=1, total_docs=40)
ck("trust index 0-100", 0<=ti<=100)
ck("trust index high for clean", tr.trust_index(100,1.0,0,40)==100)
ck("trust index low for poor", tr.trust_index(10,0.1,20,40) < 50)

print(f"\n=== {len(P)} passed, {len(F)} failed ===")
sys.exit(1 if F else 0)
