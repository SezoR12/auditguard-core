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
