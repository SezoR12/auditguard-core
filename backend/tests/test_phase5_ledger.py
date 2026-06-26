import os, sys
import os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.update({"SUPABASE_DB_HOST":"x","SUPABASE_DB_USER":"x","SUPABASE_DB_PASSWORD":"x",
 "SECRET_KEY":"x","JWT_SECRET":"x","ENCRYPTION_MASTER_KEY":"k"})
from datetime import datetime, timezone
from app.services.ledger_service import (compute_entry_hash, GENESIS_HASH,
    build_tamper_proof_certificate)

P=[];F=[]
def ck(n,c): (P if c else F).append(n); print(("PASS " if c else "FAIL ")+n)

ts = datetime(2026,6,26,10,0,tzinfo=timezone.utc)
h1 = compute_entry_hash(previous_hash=GENESIS_HASH, table_name="documents",
    record_id="r1", action="insert", old_value=None, new_value={"a":1},
    reason="x", created_by="u1", created_at=ts)
ck("hash is 64-hex sha256", len(h1)==64 and all(c in "0123456789abcdef" for c in h1))
# determinism
h1b = compute_entry_hash(previous_hash=GENESIS_HASH, table_name="documents",
    record_id="r1", action="insert", old_value=None, new_value={"a":1},
    reason="x", created_by="u1", created_at=ts)
ck("hash deterministic", h1==h1b)
# any field change -> different hash
h2 = compute_entry_hash(previous_hash=GENESIS_HASH, table_name="documents",
    record_id="r1", action="insert", old_value=None, new_value={"a":2},
    reason="x", created_by="u1", created_at=ts)
ck("new_value change -> diff hash", h1!=h2)
# chaining: prev hash matters
h3 = compute_entry_hash(previous_hash=h1, table_name="documents",
    record_id="r2", action="update", old_value={"a":1}, new_value={"a":2},
    reason="y", created_by="u1", created_at=ts)
h3b = compute_entry_hash(previous_hash="deadbeef", table_name="documents",
    record_id="r2", action="update", old_value={"a":1}, new_value={"a":2},
    reason="y", created_by="u1", created_at=ts)
ck("previous_hash affects hash", h3!=h3b)
# created_at included in hash (spec requirement)
ts2 = datetime(2026,6,26,11,0,tzinfo=timezone.utc)
h4 = compute_entry_hash(previous_hash=GENESIS_HASH, table_name="documents",
    record_id="r1", action="insert", old_value=None, new_value={"a":1},
    reason="x", created_by="u1", created_at=ts2)
ck("created_at included in hash", h1!=h4)

# tamper-proof certificate
cert = build_tamper_proof_certificate(report_id="rep-1", report_content="hello report",
    ledger_hash_at_generation=h3, company_key="companysecret")
ck("cert has required keys", {"report_id","generated_at","ledger_hash_at_generation","digital_signature"} <= set(cert))
ck("cert signature 64-hex (hmac-sha256)", len(cert["digital_signature"])==64)
# signature changes if content changes
cert2 = build_tamper_proof_certificate(report_id="rep-1", report_content="hello reportX",
    ledger_hash_at_generation=h3, company_key="companysecret")
ck("cert signature binds content", cert["digital_signature"]!=cert2["digital_signature"])

print(f"\n=== {len(P)} passed, {len(F)} failed ===")
sys.exit(1 if F else 0)
