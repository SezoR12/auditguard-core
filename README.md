# AuditCore — Phase 1

On-premise audit intelligence platform.

**Stack (hybrid):**
- **Frontend:** TanStack Start (React 19 + Vite + TailwindCSS v4, RTL by default).
- **Backend:** FastAPI 0.115 (Python 3.11, async, SQLAlchemy 2.0 + asyncpg).
- **Database:** Your external Supabase Postgres (project `zqcvwxaiblovwkjvcqmz`, ap-southeast-2).
- **Queue:** Redis 7 (for Celery later).
- **WhatsApp bridge:** Node 20 (Baileys, placeholder for Phase 2).
- All non-DB services run in Docker Compose.

## Prerequisites
- Docker + Docker Compose v2
- `openssl` (for setup.sh secret generation)
- Your Supabase DB password (stored as the secret `SUPABASE_DB_PASSWORD` in this Lovable project — also paste it into `.env` on the deploy host).
- Your Supabase **anon key** from Supabase → Project Settings → API.

## First-time setup

```bash
chmod +x setup.sh
./setup.sh          # first run — creates .env and exits
# edit .env, fill SUPABASE_DB_PASSWORD + VITE_AUDITCORE_SUPABASE_ANON_KEY
./setup.sh          # second run — boots stack, migrates, seeds
```

Then:
- Backend: <http://localhost:8000/docs>
- Frontend: <http://localhost:5173>

## Seed users

| Role | Email | Password |
|---|---|---|
| owner   | `owner@auditcore.local`   | `Owner123!`   |
| gm      | `gm@auditcore.local`      | `Gm123!`      |
| manager | `manager@auditcore.local` | `Manager123!` |
| auditor | `auditor@auditcore.local` | `Auditor123!` |

## RLS verification

`backend/alembic/versions/002_enable_rls.py` performs a self-test during
`alembic upgrade head`: it inserts a probe row into `analytics_outputs`,
switches to the `auditor` role via `set_user_role('auditor')`, asserts the
SELECT returns 0 rows, then switches to `owner` and asserts ≥1 row. The
migration fails loudly if either assertion breaks.

Manual check from `psql`:

```sql
SELECT set_user_role('auditor');
SELECT count(*) FROM analytics_outputs;   -- 0

SELECT set_user_role('owner');
SELECT count(*) FROM analytics_outputs;   -- > 0
```

## Auth flow

1. Frontend POSTs `{ email, password }` to `/auth/login` → `{ access_token, refresh_token }`.
2. Tokens stored in `localStorage`. `Authorization: Bearer <jwt>` on every request.
3. `get_current_user` decodes the JWT, loads the user, and calls
   `SELECT set_config('app.current_user_role', <role>, true)` on the DB
   connection BEFORE any query runs. RLS policies on
   `analytics_outputs`/`waste_map_items`/`risk_alerts` use this setting to
   block auditors.
4. `require_role("owner", ...)` returns HTTP 403 with Arabic `detail`
   (`"ليس لديك الصلاحية للوصول إلى هذا المورد"`) if the role doesn't match.

## Running pieces separately

```bash
# Backend only
docker compose up -d backend redis

# Alembic
docker compose exec backend alembic upgrade head
docker compose exec backend alembic revision --autogenerate -m "your change"

# Reapply RLS SQL files in supabase/migrations/
docker compose exec backend python scripts/apply_rls.py

# Reseed
docker compose exec backend python scripts/seed.py
```

## Repo layout

```
docker-compose.yml
frontend.Dockerfile          # builds the TanStack app
setup.sh
.env.example
README.md
backend/
  Dockerfile
  requirements.txt
  alembic.ini
  alembic/
    env.py
    versions/
      001_initial_schema.py  # tables + enums
      002_enable_rls.py      # RLS policies + self-test
  app/
    config.py                # pydantic-settings → DATABASE_URL from Supabase parts
    database.py              # asyncpg engine + set_user_role()
    security.py              # bcrypt + JWT
    api/auth.py              # /auth/login, /auth/refresh, /auth/me
    api/deps.py              # get_current_user, require_role
    models/                  # SQLAlchemy 2.0 models
  scripts/
    seed.py
    apply_rls.py
supabase/
  migrations/
    20260625000000_auditcore_initial.sql   # SQL mirror of Alembic 001
    20260625000001_rls_auditor_hide.sql    # SQL mirror of Alembic 002
baileys-bridge/
  Dockerfile
  index.js                   # placeholder for Phase 2
src/                         # TanStack frontend
  hooks/useAuth.tsx
  lib/api.ts
  lib/supabaseClient.ts
  components/RoleDashboard.tsx
  routes/login.tsx, owner.tsx, auditor.tsx, manager.tsx, gm.tsx
```

## Important notes about the Lovable preview

This project also has **Lovable Cloud** enabled (a separate Supabase project).
The Lovable preview's auto-generated client at
`src/integrations/supabase/client.ts` points at that Cloud project, NOT at
your external Supabase. The AuditCore frontend uses
`src/lib/supabaseClient.ts` + `src/lib/api.ts` and ignores the Cloud client
entirely. To run the frontend in Lovable preview, set
`VITE_AUDITCORE_SUPABASE_URL`, `VITE_AUDITCORE_SUPABASE_ANON_KEY`, and
`VITE_AUDITCORE_API_URL` (= your reachable FastAPI URL).

---

# AuditCore — Phase 2: Secure Document Ingestion

Phase 2 adds an encrypted file ingestion pipeline. Auditors upload documents
(Excel, CSV, Word, images, PDF, encrypted JSON); each file is validated,
encrypted with **AES-256-GCM**, and stored on the local Smart Box volume.
Only metadata is kept in the database.

## What was added

**Backend**
- `app/crypto.py` — AES-256-GCM with per-file keys derived via HKDF-SHA256 from
  `ENCRYPTION_MASTER_KEY` + `company_id` + file UUID. **Keys are never stored.**
- `app/storage.py` — async (aiofiles) encrypt-and-write / read-and-decrypt.
- `app/validation.py` — extension allow-list + libmagic MIME sniffing
  (rejects e.g. an `.exe` renamed to `.pdf`).
- `app/api/documents.py` — the document API.
- `app/schemas/document.py` — request/response models + category mapping.

**Frontend**
- `src/routes/auditor.upload.tsx` — RTL drag-and-drop upload page
  (`react-dropzone`) with category dropdown, progress bar, success message,
  and an "my uploads" table.
- `src/lib/api.ts` — added `uploadDocument` (XHR w/ progress) + list helpers.

**Infra**
- `docker-compose.yml` — new persistent `auditcore_data` volume mounted at `/data`.
- `backend/Dockerfile` — installs `libmagic1`, runs as non-root `appuser`,
  owns `/data`.
- `setup.sh` / `.env.example` — generate/define `ENCRYPTION_MASTER_KEY`.

## API endpoints

| Method | Path | Roles | Purpose |
|---|---|---|---|
| POST | `/documents/upload` | auditor, manager, gm, owner, admin | multipart upload (`file`, `doc_category`, optional `branch_id`) |
| GET | `/documents/my-uploads` | any authenticated | current user's uploads, newest first |
| GET | `/documents/pending-certification` | auditor, manager, gm, owner, admin | company docs with status `pending`/`ocr_processing` |
| GET | `/documents/company` | owner, gm, manager, admin | all company documents (broad scope) |

### Upload rules
- Max size **50 MB**.
- Allowed extensions: `.xlsx .csv .docx .jpg .jpeg .png .tiff .pdf .json`.
- The sniffed MIME must match the extension or the upload is rejected (HTTP 400,
  Arabic message).
- `.json` uploads go through the **encrypted-JSON pipeline**: the file must be a
  JSON object containing top-level `metadata` and `encrypted_payload` keys. It is
  stored as-is and flagged (`extracted_data.encrypted_json = true`); it is **not**
  decrypted (a later phase's AI engine does that).

## On-disk layout

```
/data/uploads/company_{company_id}/{YYYY}/{MM}/{uuid}_{filename}
```

Each file starts with the magic bytes `AGEC1` followed by version, salt, nonce,
then ciphertext+GCM tag. Opening it directly shows binary garbage, not the
original content. Files are written `chmod 600` and owned by the non-root
container user.

## Environment

```
STORAGE_ROOT=/data
ENCRYPTION_MASTER_KEY=<64-hex chars; generated by setup.sh>
```

⚠️ Changing `ENCRYPTION_MASTER_KEY` makes previously stored files
**undecryptable**. Back it up securely.

## Local backend tests

The crypto/validation/storage logic is covered by a standalone script that
verifies: encryption round-trip, on-disk ciphertext is not the original bytes,
MIME-mismatch rejection, disallowed extensions, and encrypted-JSON structure
preservation. (See commit notes; run inside the backend venv.)

---

# AuditCore — Phase 3: OCR & Human-in-the-Loop Certification

Phase 3 adds Arabic OCR and the auditor's certification workflow: a background
worker extracts fields from uploaded invoices, color-codes them by confidence,
and the auditor reviews a split-screen view (original on the right, fields on the
left), corrects red/yellow fields, and certifies. Every certification is written
to a tamper-evident hash-chained ledger.

## What was added

**Backend**
- `app/ocr.py` — Tesseract (Arabic `ara+eng`) text extraction, invoice field
  parsing (invoice_number, date, amount, vendor_name, items_list), confidence
  color-coding (green ≥85, yellow 60–84, red <60/missing). Pure functions are
  unit-tested without Tesseract.
- `app/workers/ocr_worker.py` — decrypts a document **in memory only**, runs OCR,
  saves `extracted_data` + `confidence_score`, sets status → `ocr_processing`.
  Registered as the Celery task `ocr.run_ocr_for_document` (with retry +
  exponential backoff). The upload endpoint enqueues via `enqueue_ocr()`; if the
  broker is unreachable it falls back to an in-process FastAPI BackgroundTask.
- `app/celery_app.py` — central Celery app (Redis broker + result backend),
  `ocr` queue, sensible time limits. Run the worker with:
  `celery -A app.celery_app.celery_app worker --loglevel=info -Q ocr`
  In Docker this is the dedicated **`worker`** service (shares the backend image,
  the `/data` volume, and `.env`).
- `app/ledger.py` — SHA-256 hash-chain helpers (`append_entry`, `verify_chain`).
  Each entry hashes its persisted columns + the previous hash, so the chain is
  verifiable from the DB alone.
- `app/api/certification.py` —
  - `GET /certification/next` → oldest `ocr_processing` doc for the company,
    with the decrypted original as a base64 data URL + `extracted_data`/flags.
  - `POST /certification/{doc_id}/certify` → saves corrections, marks
    `certified`, sets confidence to 100, writes a ledger entry, and calls the
    (placeholder) AI-analysis trigger.

**Frontend (TanStack Start)**
- `src/routes/auditor.certify.tsx` — RTL split-screen review. Right: original
  image/PDF. Left: fields colored by confidence (green editable, yellow warning,
  red required). The **[تأكيد واعتماد المستند]** button is disabled until all red
  fields are filled. After certifying, the next document auto-loads
  (assembly-line). Arabic labels: رقم الفاتورة، التاريخ، المبلغ، اسم المورد، البنود.
- `src/lib/api.ts` — `nextCertification` + `certify` helpers and types.

**Infra**
- `backend/Dockerfile` — installs `tesseract-ocr tesseract-ocr-ara poppler-utils`.
- `requirements.txt` — `pytesseract`, `pdf2image`, `Pillow`.

## Pipeline / status flow

```
upload (image|pdf)  --> status=pending
   └─ enqueue_ocr() → Celery task ocr.run_ocr_for_document (queue "ocr")
        run by the dedicated `worker` container
        (falls back to an in-process BackgroundTask if the broker is down)
        decrypt in memory → Tesseract(ara+eng) → parse → flags
        --> status=ocr_processing  (ready for human review)
auditor GET /certification/next → corrects red/yellow → POST .../certify
   --> status=certified, confidence=100
   --> document_certifications row
   --> audit_ledger entry (action=insert, SHA-256 chained)
   --> AI-analysis placeholder (no-op; Zero-Knowledge preserved)
```

## Security notes
- Decrypted bytes never touch disk — OCR and image display work from in-memory
  `bytes` / base64 only.
- The OCR worker binds an `admin` RLS role (not `auditor`), and the certify flow
  never reads analytics/waste/risk tables — **auditors remain zero-knowledge**.

## Local tests
- `backend/tests/test_phase3_logic.py` — 17 checks: confidence flagging, Arabic
  field parsing (incl. Arabic-digit normalization), `extracted_data` shape, and
  ledger hash-chain validity + tamper/linkage detection. All passing.
- End-to-end OCR was verified against a rendered Arabic invoice image with real
  Tesseract 5 + the `ara` language pack (text + confidence extracted; encrypt →
  store → decrypt → OCR round-trip confirmed; no plaintext written to disk).
