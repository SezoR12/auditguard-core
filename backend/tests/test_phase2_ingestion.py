import asyncio, os, sys, json, struct
import os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Minimal env so config import works
os.environ.update({
    "SUPABASE_DB_HOST":"x","SUPABASE_DB_USER":"x","SUPABASE_DB_PASSWORD":"x",
    "SECRET_KEY":"x","JWT_SECRET":"x",
    "STORAGE_ROOT":"/tmp/auditcore_data",
    "ENCRYPTION_MASTER_KEY":"test-master-key-abc123",
})

from app.crypto import encrypt_bytes, decrypt_bytes, MAGIC
from app.validation import validate_upload
from app.models.enums import FileType
from app import storage

PASS=[]; FAIL=[]
def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ")+name)

# --- 1. Crypto round trip ---
pt = b"hello secret invoice data " * 100
blob = encrypt_bytes(pt, master_key="mk", company_id="c1", file_uuid="f1")
check("crypto: blob starts with magic", blob[:5]==MAGIC)
check("crypto: ciphertext != plaintext", pt not in blob)
rt = decrypt_bytes(blob, master_key="mk", company_id="c1", file_uuid="f1")
check("crypto: round-trip matches", rt==pt)

# wrong context fails (auth)
try:
    decrypt_bytes(blob, master_key="mk", company_id="WRONG", file_uuid="f1")
    check("crypto: wrong company rejected", False)
except Exception:
    check("crypto: wrong company rejected", True)

# --- 2. A real PNG: validation + on-disk encryption ---
# Minimal valid PNG (1x1) 
png = bytes.fromhex(
 "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
 "890000000a49444154789c6360000002000154a24f3e0000000049454e44ae426082")
ft, mime = validate_upload("invoice.png", png)
check("validate: png recognized as image", ft==FileType.image and mime=="image/png")

async def run_storage():
    rel = await storage.save_encrypted(plaintext=png, company_id="comp1",
                                       file_uuid="uuid-png", filename="invoice.png")
    abspath = storage.absolute_path(rel)
    on_disk = open(abspath,"rb").read()
    check("storage: path layout uploads/company_/year/month", "uploads/company_comp1/" in rel)
    check("storage: on-disk is NOT the original png (encrypted)", on_disk[:8]!=png[:8] and png not in on_disk)
    check("storage: on-disk begins with AGEC magic", on_disk[:5]==MAGIC)
    dec = await storage.load_decrypted(relative_path=rel, company_id="comp1", file_uuid="uuid-png")
    check("storage: decrypt restores exact png bytes", dec==png)
asyncio.run(run_storage())

# --- 3. MIME mismatch: an EXE/script renamed to .pdf must be rejected ---
fake = b"MZ\x90\x00\x03"+b"\x00"*100  # PE/EXE header
try:
    validate_upload("malware.pdf", fake)
    check("validate: exe-as-pdf rejected", False)
except ValueError as e:
    check("validate: exe-as-pdf rejected", str(e).startswith("mime_mismatch"))

# disallowed extension
try:
    validate_upload("a.exe", fake)
    check("validate: .exe extension rejected", False)
except ValueError as e:
    check("validate: .exe extension rejected", str(e)=="extension_not_allowed")

# --- 4. Encrypted JSON envelope ---
good = json.dumps({"metadata":{"v":1},"encrypted_payload":"BASE64=="}).encode()
ft2, mime2 = validate_upload("acct.json", good)
check("validate: json -> encrypted_json filetype", ft2==FileType.encrypted_json)
parsed = json.loads(good.decode())
check("encjson: envelope has required keys", "metadata" in parsed and "encrypted_payload" in parsed)
# round-trip through storage preserves structure
async def run_json():
    rel = await storage.save_encrypted(plaintext=good, company_id="comp1",
                                       file_uuid="uuid-json", filename="acct.json")
    dec = await storage.load_decrypted(relative_path=rel, company_id="comp1", file_uuid="uuid-json")
    check("encjson: structure preserved through encrypt/decrypt", json.loads(dec.decode())==parsed)
asyncio.run(run_json())

print(f"\n=== {len(PASS)} passed, {len(FAIL)} failed ===")
sys.exit(1 if FAIL else 0)
