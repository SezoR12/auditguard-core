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

## Tenant isolation RLS (users · tasks · documents · ledger)

Beyond the auditor zero-knowledge policies, company/branch isolation is enforced
at the DB layer (migrations `008`/`009`, SQL mirrors `20260626000004` /
`20260626000005`):

- **`users`** — read your own profile; owner/gm/manager read users in their own
  company; only owner/admin/appowner may change a `role` (trigger blocks
  self-escalation).
- **`audit_tasks`** — auditors see only their own assigned tasks; managers are
  scoped to company **+ branch**; owner/gm to company; admin/appowner = all.
- **`documents` / `document_certifications`** — company isolation; auditors may
  only attribute a certification to themselves.
- **`audit_ledger`** — global append-only hash-chain: `SELECT`/`INSERT` open,
  `UPDATE`/`DELETE` denied for everyone (immutable).

These read a per-request session context set in `app/api/deps.py` via
`set_user_context` (role, user id, company, branch, auth sub/email) consumed by
SQL accessors `public.current_app_*()`. Proven live by
`backend/tests/test_phase14_rls_auth.py` (36 checks, run as non-superuser).

> **RLS only enforces under a non-superuser DB role.** In production you must
> switch `SUPABASE_DB_USER` from the Supabase pooler superuser (which has
> `BYPASSRLS`) to a dedicated `appuser`. See **SECURITY.md → "Provisioning the
> runtime DB role"**.

### Frontend route guards

Protected routes block rendering until `/auth/me` resolves, then redirect:
unauthenticated → `/login`; authenticated-but-wrong-role → the user's **own**
role dashboard (`roleHomePath`). Implemented by `src/components/RequireRole.tsx`
(and the role-aware `RoleDashboard` / `OwnerShell`). This is a UX layer — the
real enforcement is backend `require_role` + DB RLS.

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

---

# AuditCore — Phase 4: Daily Task Engine & Penalty System

Phase 4 adds the productivity engine: tasks auto-generate each morning for every
auditor, a live countdown drives urgency, missed SLAs auto-apply demerit points,
and the Owner gets a performance preview.

## What was added

**Backend**
- `app/services/sla.py` — pure logic: Baghdad timezone (UTC+3), SLA durations
  (OCR 4h, bank statements 24h, reversals 2h, custom configurable), demerit
  values (critical 3 / normal 1), `time_color` (green / yellow <50% / red
  overdue), and the efficiency formula
  `(on_time / total) * 100 - (demerits * 5)` (clamped 0–100).
- `app/services/task_generator.py` — builds tasks from real backlog signals:
  pending OCR certifications, missing previous-month bank statements, reverse
  entries. Idempotent per Baghdad day.
- `app/services/performance.py` — demerit application, `auditor_performance`
  upsert, and `check_overdue()`.
- `app/api/tasks.py` —
  - `GET /tasks/my-tasks` (today's tasks + `time_remaining_seconds` + color)
  - `POST /tasks/{id}/complete` (records `completed_at`, stops SLA timer,
    updates performance)
  - `GET /tasks/overdue-check` (internal; penalizes overdue tasks)
  - `POST /tasks/generate-daily` (internal/admin)
- `app/api/owner.py` — `GET /owner/auditor-performance` (today's table:
  completed, delayed, demerits, efficiency).
- `app/models/auditor_performance.py` + migration `003_tasks_performance`
  (Alembic) and `db/migrations/20260626000000_tasks_performance.sql` (adds the
  `is_critical` flag on `audit_tasks` and the `auditor_performance` table).

**Scheduling (Celery Beat)**
- `app/workers/task_worker.py` — Celery tasks `tasks.generate_daily` and
  `tasks.check_overdue`.
- `app/celery_app.py` — beat schedule:
  - `tasks.generate_daily` at **05:00 UTC == 08:00 Asia/Baghdad** daily
  - `tasks.check_overdue` every **15 minutes**
  - new `tasks` queue (worker now consumes `-Q ocr,tasks`).
- `docker-compose.yml` — new **`beat`** service (`celery ... beat`) and the
  `worker` now also drains the `tasks` queue.

**Frontend (TanStack Start)**
- `src/routes/auditor.tasks.tsx` — RTL task table with **live countdown**,
  color-coded rows (green/yellow/red), an **[إنجاز]** button, and the summary
  "المهام المنجزة | المتأخرة | النقاط السلبية".
- `src/routes/owner.performance.tsx` — RTL performance table for the Owner.
- `src/lib/api.ts` — `myTasks`, `completeTask`, `auditorPerformance` + types.

## Acceptance criteria — status
- ✅ 08:00 Baghdad → tasks auto-generate (Celery Beat crontab at 05:00 UTC).
- ✅ Auditor sees tasks with a per-second countdown timer.
- ✅ Missed SLA → demerit auto-applied within 15 min (`check_overdue` beat).
- ✅ Owner views the performance table (delays + efficiency).
- ✅ Completing a task sets status/`completed_at` and stops the timer.

## Local tests
- `backend/tests/test_phase4_sla.py` — 21 checks on SLA, color, demerits,
  efficiency. All passing.
- A full DB integration run (local Postgres) verified: generation →
  completion → forced overdue → `check_overdue` → `auditor_performance`
  aggregation (efficiency `1/2*100 - 3*5 = 35.0`) → idempotent re-generation.

---

# AuditCore — Phase 5: Tamper-Proof Audit Trail

Phase 5 hardens the trust layer: every critical action is cryptographically
chained (SHA-256), and the Owner can prove no one tampered with history.

## What was added

**Backend**
- `app/services/ledger_service.py` — the canonical ledger service:
  - `append_ledger_entry(...)` — fetches the last `current_hash` and computes
    `current_hash = SHA-256(previous_hash + json.dumps({table_name, record_id,
    action, old_value, new_value, reason, created_by, created_at}, sort_keys=True))`.
    `created_at` is set in Python (UTC, tz-aware) and stored, so the chain is
    re-verifiable from the DB alone.
  - `verify_ledger_integrity()` — re-walks the whole chain, recomputes each
    hash, checks linkage, returns `{is_valid, total_entries, broken_links,
    last_verified_at}`.
  - `build_tamper_proof_certificate(...)` — report_id, generated_at,
    ledger_hash_at_generation, and an HMAC-SHA256 `digital_signature` over the
    report content using the company key (for Phase 9 exports).
- `app/services/audit_log.py` — service-layer auto-logging helpers used by the
  API endpoints (async-safe; carry the acting user + RLS role). Logs:
  - `documents` insert (upload) and update (certification),
  - `document_certifications` insert,
  - `audit_tasks` status changes (completion + overdue).
  - Corrections use the Arabic reason
    `تصحيح OCR: تغيير [field] من [old] إلى [new]`.
- `app/api/ledger.py` — **Owner-only**, read/verify only (the ledger is
  append-only; no update/delete endpoint exists anywhere):
  - `GET /owner/ledger` — paginated + filterable (table, user, date range),
    each row carries `chain_status` (valid/invalid) computed from genesis.
  - `GET /owner/ledger/verify` — runs full verification.

> Why service-layer hooks instead of SQLAlchemy `@event.listens_for`: the engine
> is async (ORM events can't `await` the ledger INSERT) and the acting user /
> RLS role live in the request context, not the flush. The hooks are invoked
> from each mutating endpoint so logging is reliable and attributable.

**Frontend (TanStack Start)**
- `src/routes/owner.ledger.tsx` — RTL ledger viewer: table (التاريخ، المستخدم،
  الجدول، العملية، السبب، رمز التحقق، الحالة), a **[التحقق من سلامة السلسلة]**
  button showing green "السجل سليم 100%" or a red broken-link alert, and filters
  by table / date range.
- `src/lib/api.ts` — `ledger()`, `verifyLedger()` + types; owner dashboard link.

## Acceptance criteria — verified
- ✅ Upload → ledger entry with valid hash (first entry chains from genesis).
- ✅ Certify → ledger entry whose `previous_hash` matches the last entry.
- ✅ `/owner/ledger/verify` → `is_valid=true`, chain intact.
- ✅ Manually editing a ledger hash in the DB → verify returns `is_valid=false`
  with the broken link(s) identified.
- ✅ Owner views the full chronological chain with user attribution.

## Local tests
- `backend/tests/test_phase5_ledger.py` — 8 checks: hashing determinism,
  every-field sensitivity (incl. `created_at`), chaining, and the HMAC
  certificate.
- A full DB integration run (local Postgres, 12 checks) proved: upload →
  certify (doc update + cert insert) → intact verification → **DB tamper →
  verify detects it** (flags the edited entry and the now-broken next link).

---

# AuditCore — Phase 6: The Silent Engine (AI Analytics)

Phase 6 adds the background analytics brain. It runs entirely inside the backend
container (no external AI APIs), using pandas/numpy/scikit-learn, and writes only
to RLS-protected tables auditors can never read.

## Modules (`backend/app/ai/`)
- `common.py` — parse certified `extracted_data.fields` into typed `InvoiceRecord`s
  (Arabic-digit/amount/date parsing). Pure, testable.
- `data_quality.py` — DataQualityGuard: duplicate invoice numbers per vendor,
  missing mandatory fields, out-of-sequence serials, invalid amounts → quality
  flags + a 0–100 quality score.
- `anomaly.py` — AnomalyDetector (needs ≥30 docs for baseline): Z-score>3 on
  amounts, IQR outliers on unit prices, serial-number gaps, weekend spikes
  (Fri/Sat). → risk_alerts.
- `cross_reference.py` — CrossReferencer: procurement vs bank outflow (1%
  tolerance), procurement vs inventory quantities (5% tolerance) → variance
  findings.
- `impact.py` — FinancialImpactCalculator: maps anomalies + findings +
  duplicates to IQD `waste_map_items` (financial/operational/opportunity).
- `predictor.py` — Predictor: next-month cash outflow (linear regression /
  moving-average fallback) + inventory consumption rate.
- `narrative.py` — NarrativeGenerator: template-based Arabic summaries
  (owner: "تم رصد هدر بقيمة X د.ع …", manager: "يوجد لديك N مهمة تصحيح مفتوحة …").
- `trust.py` — Trust Index (0–100): `0.6*quality + 0.4*coverage*100 − anomaly_penalty`.
- `orchestrator.py` — `run_analysis_for_company()` runs steps 1–8 and persists
  risk_alerts, cross_reference_findings, waste_map_items, analytics_outputs
  (prediction / narrative / daily_snapshot). Binds a non-auditor RLS role so it
  can write (and auditors still can't read).

## Scheduling & API
- Celery task `analysis.run_daily` (queue `analysis`) on Beat at **23:00 UTC ==
  02:00 Asia/Baghdad**; worker now drains `-Q ocr,tasks,analysis`.
- `app/workers/analysis_worker.py` — `analysis.run_daily`,
  `analysis.run_for_company`.
- `POST /admin/run-analysis?company_id=&inline=true` — manual trigger
  (owner→own company; admin→any/all). `inline=true` runs in-process for testing;
  otherwise enqueues Celery.

## New schema (migration 004 + SQL mirror)
- `cross_reference_findings` table (RLS: auditor-hidden, same policy pattern).
- `output_type` enum += `prediction`, `narrative`, `daily_snapshot`.

## Acceptance criteria — verified
- ✅ Certify 10+ invoices → run analysis → `waste_map_items` populated with IQD
  amounts (integration test: 15 docs → 3 waste items, total 6.66M IQD).
- ✅ Mismatched procurement vs inventory → `cross_reference_findings` with
  variance (both procurement_vs_bank and procurement_vs_inventory produced).
- ✅ Duplicate invoice → flagged → duplicate-payment waste recorded.
- ✅ Trust Index calculated + stored (snapshot trust_index=95 in the test).
- ✅ **Auditor account cannot read any AI output table** — verified via RLS:
  auditor role sees 0 rows in waste_map_items / risk_alerts /
  cross_reference_findings / analytics_outputs, while owner sees them.

## Tests
- `backend/tests/test_phase6_ai.py` — 24 pure-logic checks (parsing, quality,
  anomaly baseline + outliers, cross-ref variance, impact, predictions,
  narratives, trust index).
- Full DB integration (local Postgres, 14 checks) incl. the RLS zero-knowledge
  verification above.

---

# AuditCore — Phase 7: Owner 4-Layer Dashboard

The Owner command center with progressive drill-down: bird's-eye → department →
AI findings → raw source.

## Backend (`app/api/owner_dashboard.py`, owner/management only)
- `GET /owner/dashboard/layer1` — 5 executive metrics: monthly waste (IQD, with
  MoM trend), trust index (latest snapshot), open critical alerts, predicted
  next-month cash, avg auditor efficiency.
- `GET /owner/dashboard/layer2` — waste per department + category breakdown
  (financial/operational/human/opportunity).
- `GET /owner/dashboard/layer3` — narratives, cross-reference findings, anomalies;
  filterable by department / severity / date range.
- `GET /owner/dashboard/layer4/{document_id}` — raw source: decrypted original
  image (base64), certified extracted data, certification history (auditor +
  corrections), and the linked hash-chained ledger entries, with user attribution.

All four reuse `require_role("owner","gm","admin","appowner")`; the underlying
analytics/waste/risk/cross-ref tables are RLS-protected, so an auditor token is
both 403'd at the API and would see zero rows at the DB.

## Frontend (TanStack Start + Recharts, RTL)
- `/owner` (Layer 1) — 5 cards with big numbers, trend arrows, [تفاصيل] drill.
- `/owner/departments` (Layer 2) — bar chart (waste by dept) + pie (categories) +
  ranked table; click a department → analytics.
- `/owner/analytics` (Layer 3) — AI narrative summary, cross-reference + anomaly
  tables, severity filter; click a finding (with a document_id) → raw data.
- `/owner/raw-data` (Layer 4) — original image, certified fields, certification
  log, linked ledger — "هذا هو السجل الأصلي".
- Shared `OwnerShell` (auth + role guard + refresh), `useAutoRefresh` (5-min
  auto-refresh + manual), Arabic loading state "جاري تحليل البيانات...".
- Colors: blue=trust, red=waste/risk, green=opportunity.

## Acceptance criteria — verified
- ✅ Owner login → Layer 1 with 5 key numbers.
- ✅ Waste card [تفاصيل] → Layer 2 department breakdown.
- ✅ Department → Layer 3 cross-reference findings (department-scoped).
- ✅ Finding → Layer 4 original invoice image + certification history.
- ✅ RLS: auditor token → 403 on every dashboard endpoint (integration-tested).

## Tests
- `backend/tests/test_phase7_dashboard.py` — DB integration via the real ASGI
  app: seeds + runs Phase-6 analysis, then asserts all 4 layers return correct
  aggregates (5 cards, departments, categories, narratives, cross-ref, decrypted
  Layer-4 image + uploader attribution) and that an auditor JWT is 403 on all
  four endpoints.

---

# AuditCore — Phase 8: Silent Early Warning (Alerts, Digest, WhatsApp)

Real-time alerts for critical anomalies, a 07:00 daily digest, and WhatsApp
delivery via a Baileys bridge — with an offline Redis queue.

## Backend
- `services/notify_templates.py` — Arabic templates (critical / digest / overdue),
  DND window (Baghdad 23:00–06:00, configurable), phone normalization (Iraq 964).
- `services/whatsapp.py` — POSTs to the Baileys bridge `/send-message`; on any
  failure pushes to Redis list `whatsapp:queue`; `flush_queue()` retries.
- `services/alert_service.py` — severity routing: critical → in-app + immediate
  WhatsApp (unless DND); high → in-app (+ digest); low → in-app only. Recipients
  = owners + GMs (never auditors). Also `handle_task_overdue`.
- `services/digest_service.py` — per-owner daily digest (yesterday's waste,
  completed/overdue tasks, open alerts, latest trust index); idempotent per day.
- Hooks: orchestrator routes each `risk_alert` through the classifier; the
  overdue checker notifies owners/GM of late tasks.
- `workers/notify_worker.py` + beat: `notify.daily_digest` at 04:00 UTC (07:00
  Baghdad), `notify.flush_whatsapp_queue` every 5 min; worker drains
  `-Q ocr,tasks,analysis,notify`.
- `api/notifications.py` — `GET /owner/notifications`,
  `POST /owner/notifications/{id}/read`, `POST /owner/notifications/read-all`,
  `GET /owner/daily-digests`. `POST /admin/run-digest` for manual runs.
- Migration 006 + SQL mirror: `notifications`, `daily_digests`,
  `users.whatsapp_phone` — notifications & digests are RLS auditor-hidden.

## Baileys bridge (`baileys-bridge/`)
- `@whiskeysockets/baileys` + express. Multi-file auth in `/data/whatsapp_auth`
  (persistent volume → session survives restarts). QR shown in logs + `GET /qr`
  (PNG data URL). `POST /send-message {to,message}`; returns 503 when not yet
  linked so the backend queues. `GET /status` for health.

## Frontend
- `components/NotificationBell.tsx` — bell + unread badge in the owner header,
  dropdown list with severity dots + timestamps, click → drills to the relevant
  layer, mark-one / mark-all read, polls every minute.

## Acceptance criteria — verified
- ✅ Critical alert → in-app notification + WhatsApp dispatch (integration test).
- ✅ Bridge offline → queued in Redis → sent on `flush_queue` when restored
  (queue drains).
- ✅ Daily digest with correct aggregates, stored + WhatsApp'd.
- ✅ Owner sees bell with unread count; auditor gets 403 on all alert endpoints
  and 0 rows via RLS.

## Tests
- `tests/test_phase8_notify.py` — 13 logic checks (templates, DND, phone).
- `tests/test_phase8_notify_db.py` — 20-check DB integration via the real ASGI
  app + live Redis + a mocked bridge: critical→notify+WA, offline→queue→flush,
  low→in-app only, digest, notification API, and auditor 403 + RLS.

---

# AuditCore — Phase 9: Manager Tools, Export Engine, What-If Simulator

## Manager modular dashboard (`/manager`)
- `api/manager.py` — `GET /manager/widgets` (catalog) + `GET /manager/widget/{key}`
  for: budget_status, open_tasks, dept_quality_index, team_performance,
  pending_corrections.
- **Department boundary enforced in the API**: a manager is locked to their own
  `branch_id` (auditors in that branch); owners/GM may pass `branch_id` or see
  company-wide. Verified with a 2-branch company (manager sees branch A's 2
  tasks, not branch B's 3).
- Frontend: widget-selection modal, add/remove/reorder, choices persisted in
  localStorage; RTL, color-coded.

## Export engine (`services/export_service.py`)
- Excel (openpyxl): `sheet_view.rightToLeft = True`, styled headers, plus a
  **شهادة عدم التلاعب** (tamper-proof certificate) sheet.
- PDF (reportlab): embeds the bundled **Amiri** Arabic font; Arabic is reshaped +
  bidi-reordered; certificate page appended.
- PNG (matplotlib): 300 DPI bar chart with Amiri font for Arabic labels.
- Every export embeds the Phase-5 tamper-proof certificate (last ledger hash +
  HMAC over content).
- `POST /owner/exports {output_type, format, date_from, date_to}` →
  `{download_url, filename, expires_at}`. The URL carries a **15-minute signed
  token** (HMAC, `core_tokens.py`); `GET /owner/exports/download?token=…` streams
  the file (token authorizes — no extra auth needed).
- Bundled font: `backend/app/assets/fonts/Amiri-Regular.ttf` (OFL).

## What-If simulator (`/owner/what-if`)
- `services/whatif.py` (pure): recovered = base × recovery%; monthly cash-flow =
  recovery/months − monthly cost; net profit = recovered − total cost; 6-month
  cumulative projection.
- `POST /owner/what-if` accepts a `waste_item_id` (pulls its amount) or a manual
  `base_amount_iqd`.
- Frontend: sliders (recovery %, months) + cost input, live recompute, Recharts
  line chart, and export buttons.

## Export buttons
`components/ExportButtons.tsx` ([تصدير Excel] [تصدير PDF] [تصدير صورة]) added to
the departments (waste_map) and analytics (risk_alerts) layers + what-if.

## Acceptance criteria — verified
- ✅ Manager add/remove/rearrange widgets (localStorage layout).
- ✅ Manager sees only their department (2-branch integration test).
- ✅ Waste Map → Excel opens RTL with Arabic + cert sheet.
- ✅ Chart → PNG at 300 DPI with Arabic rendered (Amiri).
- ✅ What-If 6-month cash-flow math correct (e.g. 1.2M @50%/3mo/150k →
  recovered 600k, monthly CF 150k, net profit 450k).

## Tests
- `tests/test_phase9_exports.py` — 16 checks: what-if math, signed-token
  sign/verify/expire, and Excel/PDF/PNG renderers (valid magic bytes, RTL, cert).
- `tests/test_phase9_exports_db.py` — 17-check DB integration via the ASGI app:
  manager department scoping, what-if with a real waste item, Excel/PDF/PNG
  export + signed download, and auditor 403 on manager/export/what-if.

---

# AuditCore — Phase 10: On-Premise Deployment & Hardening

Production deployment automation, backups, monitoring, and updates for the
Smart Box. (Built for the current Supabase-backed architecture; the fully
air-gapped local-Postgres path is documented in DEPLOYMENT.md.)

## Scripts
- **`install.sh`** — prerequisite checks (Docker, ≥4GB RAM, ≥100GB disk),
  interactive prompts (company, owner, Supabase details), generates a hardened
  `.env` (random `ENCRYPTION_MASTER_KEY`/`JWT_SECRET`/`SECRET_KEY`/
  `REDIS_PASSWORD`/`POSTGRES_PASSWORD`, chmod 600), brings up the stack, runs
  migrations + RLS, seeds **owner-only** (no demo data), prints login + WhatsApp
  QR steps. Target < 30 min.
- **`backup.sh`** — daily (cron 03:00): encrypted `pg_dump` (AES-256), encrypted
  `uploads` tar, `audit_ledger` CSV (+ copy to USB at `/mnt/backup_usb` if
  mounted), rotation (7 daily / 4 weekly / 12 monthly), WhatsApp success/fail
  notification.
- **`healthcheck.sh`** — every 5 min: containers running, disk >20% free,
  RAM <90%, `/health` ok, UPS status; sends a **critical WhatsApp alert** to
  owners (+ `APP_OWNER_PHONE`) on any failure.
- **`update.sh`** — pre-update backup, image snapshot, rebuild app services,
  migrate, **health-gated** with automatic rollback to the previous image.
- **`scripts/seed_production.py`** — one company + one owner, idempotent.

## Backend
- `GET /health` — deep check (DB + Redis connectivity) for external monitoring;
  returns `ok` / `degraded` with per-dependency status. (`/healthz` kept as a
  liveness probe.)

## Hardening (already in place)
- Backend container runs as **non-root** (`appuser`, uid 10001).
- Postgres/Redis are **not published** to the host (Docker-internal only).
- File-at-rest AES-256-GCM; backups AES-256; RLS zero-knowledge for auditors.

## Docs
- **DEPLOYMENT.md** — technician step-by-step (non-developer), incl. WhatsApp
  linking, cron setup, and the air-gapped local-Postgres appendix.
- **TROUBLESHOOTING.md** — failed login, forgot password, disk full, WhatsApp
  disconnected, OCR, restore-from-backup, failed update.
- **SECURITY.md** — encryption, **RLS verification commands** (incl. the
  BYPASSRLS caveat), ledger verification, key-rotation procedure.

## Verified
- All scripts pass `bash -n`; production seed compiles.
- `/health` live-tested against real Postgres + Redis: reports `ok` when both up,
  and correctly flips to `degraded` (`redis: error`, `database: error`) when a
  dependency is down.
- All prior backend suites still green.

## Deferred (documented)
- **Login rate-limiting (5/15-min lockout)** and **15-min inactivity timeout**:
  with Supabase Auth the browser authenticates against Supabase directly, so
  these belong in Supabase Auth settings + a frontend idle-logout. Tracked in
  SECURITY.md.

---

# AuditCore — Phase 11: No-Code Template Builder & CRaaS

Revenue multiplier: the App Owner builds sector-specific report templates with
no code and sells Custom Reports as a Service (CRaaS).

## Backend
- `services/criteria_library.py` — sector modules (Manufacturing OEE/defect_rate,
  Restaurants food_cost/table_turnover, Real Estate rental_yield/occupancy,
  Trading inventory_turnover/margin) as JSON schemas the builder toggles and the
  AI engine can compute.
- `services/template_engine.py` — renders a template JSON `config` (text / metric
  / table / chart / image blocks with data bindings) into an Arabic RTL PDF
  (bundled Amiri font); `resolve_data` builds the live data context from the
  company's analytics + waste rows + sector metrics; `DUMMY` powers preview mode.
- `models/template.py` + migration 007 (+ SQL mirror):
  `report_templates`, `report_requests`, `custom_reports`, and the Elite-tier
  `consolidated_entities` / `consolidated_metrics` **federation schema
  (architecture only)**. CRaaS client tables are RLS auditor-hidden.
- `api/templates.py`:
  - App Owner: `GET /templates/criteria`, `GET/POST/PUT /templates`,
    `POST /templates/{id}/preview` (dummy-data PDF), `GET /admin/report-requests`,
    `POST /admin/report-requests/{id}/deploy`.
  - Client: `POST/GET /owner/report-requests`, `GET /owner/custom-reports`,
    `POST /owner/custom-reports/{id}/generate` (live-data PDF).

## Frontend
- `/appowner` — no-code builder (name, sector toggles that inject metric blocks,
  add/remove text/table/chart/image/metric blocks), saved-templates list with
  PDF preview, and the **CRaaS request inbox** with one-click deploy.
- `/owner/custom-reports` — client requests a custom report
  ([طلب تقرير تحليلي مخصص]), sees request status, and generates PDF from any
  deployed report with their live data.
- Role routing: `appowner`/`admin` land on `/appowner`.

## Acceptance criteria — verified
- ✅ App Owner builds a template without code (JSON config via the UI) + preview.
- ✅ Template deployed to the client → appears in their Custom Reports library.
- ✅ Client generates a PDF from the custom template with their live data.
- ✅ Auditors are excluded (403 + RLS) from templates/requests/custom-reports.

## Multi-company consolidation (Elite)
Schema only, per spec: `consolidated_entities` (subsidiary Smart Boxes) and
`consolidated_metrics` (periodically federated aggregates). Federation transport
(VPN/secure pull) is intentionally **not** implemented in the MVP.

## Tests
- `tests/test_phase11_templates.py` — 8 checks: criteria library + template→PDF
  rendering (incl. chart/table blocks, empty config).
- `tests/test_phase11_templates_db.py` — 13-check DB integration via the ASGI
  app: criteria, build template, preview PDF, client request → appowner inbox →
  deploy → client library → **generate live-data PDF**, plus auditor 403 + RLS.

---

# AuditCore — Sector-Metric Calculations (AI engine wiring)

Phase 11 added the criteria library + template bindings; this wires the actual
**computation** of sector metrics into the AI engine so custom reports show real
numbers.

## How it works
- `app/ai/sector_metrics.py`:
  - `safe_eval_formula` — a restricted-AST evaluator (no `eval`, no calls,
    no attribute access, no names beyond provided variables) for the criteria
    formulas. Returns `None` on missing variables or divide-by-zero.
  - `collect_base_inputs` — aggregates the **extra numeric fields** auditors
    capture in `extracted_data.fields` (beyond standard invoice fields), e.g.
    `revenue`, `cogs`, `occupied_units`, `total_units`, `annual_rent`,
    `property_value`, summed across all certified docs.
  - `compute_sector_metrics` — evaluates every metric for the active sectors;
    a metric is emitted only when **all** its variables exist (no misleading
    partial numbers).
  - `sectors_for_company` — maps the company's free-text sector (Arabic/English)
    to criteria-library module keys.
- `app/ai/common.py` — `InvoiceRecord` now carries `raw_fields` (the full parsed
  field dict) so base variables are available.
- `app/ai/orchestrator.py` — Step 7b computes `sector_metrics` and stores them in
  the daily snapshot's `data.sector_metrics` (which `template_engine.resolve_data`
  and the Owner dashboard already read), and returns them from the run.

## Example
A real-estate company whose certified reports carry `occupied_units` /
`total_units` / `annual_rent` / `property_value`:
- `occupancy_rate = Σoccupied / Σtotal × 100`
- `rental_yield = annual_rent / property_value × 100`
These appear automatically in any template that binds `occupancy_rate` /
`rental_yield`.

## Tests
- `tests/test_phase12_sector_metrics.py` — 20 checks: safe evaluator (incl.
  injection/attribute-access rejection, div-by-zero), base-input aggregation,
  real computations (occupancy 75%, margin 40%, inventory_turnover 3), and
  sector mapping.
- `tests/test_phase12_sector_metrics_db.py` — 7-check integration: real-estate
  company → analysis computes occupancy 85% / rental_yield 8% → persisted in the
  snapshot → template engine resolves them → custom-report PDF renders.

---

# AuditCore — Auth Hardening (login rate-limiting + idle timeout)

Completes the deferred Phase-10 hardening item.

## Login rate-limiting (server-side, 5 attempts / 15-min lockout)
The SPA can authenticate directly with Supabase, which the backend never sees —
so we added a **rate-limited login proxy**:
- `POST /auth/login` (backend) forwards the password grant to Supabase
  server-side. Failed attempts are counted per **email+client-IP** in Redis
  (`app/services/rate_limit.py`). After `LOGIN_MAX_ATTEMPTS` (default 5) the key
  is locked for `LOGIN_LOCKOUT_MINUTES` (default 15) → **HTTP 429** with a
  `Retry-After` header and an Arabic message. A successful login clears the
  counter. While locked, even a correct password is refused.
- The frontend `useAuth.login` now calls this proxy and sets the Supabase
  session from the returned tokens, **falling back** to direct Supabase login if
  the proxy is unreachable (so a not-yet-deployed backend doesn't block login).
- Config: `SUPABASE_ANON_KEY` (backend, = the frontend anon key),
  `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES`.

## 15-minute idle session timeout
`AuthProvider` (frontend) starts a 15-minute inactivity timer when logged in,
reset on mouse/keyboard/scroll/touch/visibility activity; on expiry it signs the
user out. Configurable via `SESSION_IDLE_TIMEOUT_MINUTES` (mirrored client-side).

## Verified
- `tests/test_phase13_auth_hardening.py` — 8 checks (needs Redis): 4 bad
  attempts → 401 (Arabic, remaining count), 5th → **429 lockout** with
  `Retry-After`, correct password refused while locked, cleared on success,
  success returns tokens. Registered in `run_tests.sh` + CI.
- Full runner: 16 suites / 250 checks pass; frontend tsc + build clean.

> Note: this throttles the backend proxy. Supabase's own public auth endpoint
> can still be called directly; for defense-in-depth also enable Supabase's
> built-in auth rate limits in the project dashboard.

---

# AuditCore — Branch Protection + Token Denylist

## Contributing / PR workflow
AuditCore uses a **pull-request workflow** — see
[`CONTRIBUTING.md`](CONTRIBUTING.md). Create a `feat/…`/`fix/…`/`docs/…` branch,
test it for real, open a PR against `main`, and let CI's two required checks gate
the merge. A PR template (`.github/pull_request_template.md`) prompts for
testing/migration/secret-hygiene confirmation. Direct pushes to `main` are
discouraged (and flagged as a rule bypass for admins).

## Branch protection (CI required on PRs)
`main` is protected (applied via the GitHub API; re-apply with
`scripts/setup_branch_protection.sh`, needs an admin token):
- Required status checks (must pass before merge): **Backend tests (pure + DB
  integration)** and **Frontend build + type-check**.
- `strict` (branch must be up to date), PRs required, force-pushes & deletions
  blocked. `enforce_admins=false` so the Lovable sync / admins aren't broken;
  flip it on for full strictness.

To require it for everyone (incl. admins): re-run with `enforce_admins=true`,
or toggle in GitHub → Settings → Branches → Branch protection rules.

## Server-side token denylist (hard revocation)
Beyond the client idle-logout, tokens can be hard-revoked server-side
(`app/services/token_denylist.py`, Redis), checked in `get_current_user`:
- `POST /auth/logout` — denies the presented access token until its own `exp`
  (the SPA logout now calls this before clearing the session).
- `POST /auth/revoke-user/{auth_user_id}` (owner/admin) — revokes ALL of a
  user's sessions by setting a "revoke before" cutoff; any token with
  `iat <= cutoff` is rejected. Use after password reset / suspected compromise.
- Fails **open** if Redis is unavailable (availability over revocation) — change
  in `is_denied` if you need fail-closed.

Verified: `tests/test_phase13_token_denylist_db.py` — 6 checks (token revoke →
401, fresh token still valid, user-wide revoke kills existing sessions, tokens
issued after the cutoff accepted). Full runner: 17 suites / 256 checks pass.

> For defense-in-depth, also enable Supabase's built-in auth rate limits in the
> project dashboard (Authentication → Rate Limits) — those guard Supabase's own
> public auth endpoint, which the backend proxy cannot.
