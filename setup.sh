#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# AuditCore Phase 1 — setup script
# Brings up the on-prem stack and points it at the external
# Supabase Postgres defined in .env.
# ============================================================

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
red() { printf "\033[31m%s\033[0m\n" "$*"; }

bold "→ Checking Docker..."
command -v docker >/dev/null 2>&1 || { red "Docker is not installed."; exit 1; }
docker compose version >/dev/null 2>&1 || { red "Docker Compose v2 is not installed."; exit 1; }
green "  Docker OK"

if [ ! -f .env ]; then
  bold "→ No .env found, generating one from .env.example"
  cp .env.example .env

  # Random secrets
  SECRET_KEY=$(openssl rand -hex 32)
  ENCRYPTION_MASTER_KEY=$(openssl rand -hex 32)
  sed -i.bak "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" .env
  sed -i.bak "s|^ENCRYPTION_MASTER_KEY=.*|ENCRYPTION_MASTER_KEY=${ENCRYPTION_MASTER_KEY}|" .env
  rm -f .env.bak

  red "⚠  Edit .env and set SUPABASE_DB_PASSWORD, SUPABASE_JWT_SECRET, SUPABASE_SERVICE_ROLE_KEY, and VITE_AUDITCORE_SUPABASE_ANON_KEY, then re-run ./setup.sh"
  exit 1
fi

# shellcheck disable=SC1091
set -a; source .env; set +a

if [ -z "${SUPABASE_DB_PASSWORD:-}" ] || [ "${SUPABASE_DB_PASSWORD}" = "replace-me-with-the-real-password" ]; then
  red "✗ SUPABASE_DB_PASSWORD is not set in .env"
  exit 1
fi
if [ -z "${SUPABASE_JWT_SECRET:-}" ] || [[ "${SUPABASE_JWT_SECRET}" == replace-* ]]; then
  red "✗ SUPABASE_JWT_SECRET is not set in .env (Supabase Project Settings → API → JWT Settings)"
  exit 1
fi
if [ -z "${SUPABASE_SERVICE_ROLE_KEY:-}" ] || [[ "${SUPABASE_SERVICE_ROLE_KEY}" == replace-* ]]; then
  red "✗ SUPABASE_SERVICE_ROLE_KEY is not set in .env (needed by seed script)"
  exit 1
fi

bold "→ Building and starting containers..."
docker compose up -d --build

bold "→ Waiting for backend to come up..."
for i in {1..30}; do
  if docker compose exec -T backend python -c "print('ok')" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

bold "→ Running Alembic migrations against Supabase..."
docker compose exec -T backend alembic upgrade head

bold "→ Applying RLS policies (supabase/migrations)..."
docker compose exec -T backend python scripts/apply_rls.py

bold "→ Seeding initial users and company..."
docker compose exec -T backend python scripts/seed.py

green ""
green "============================================================"
green "  AuditCore is up."
green "============================================================"
green "  Backend:  http://localhost:8000/docs"
green "  Frontend: http://localhost:5173"
green ""
green "  Login credentials (seed):"
green "    owner@auditcore.local     Owner123!"
green "    gm@auditcore.local        Gm123!"
green "    manager@auditcore.local   Manager123!"
green "    auditor@auditcore.local   Auditor123!"
green "============================================================"
