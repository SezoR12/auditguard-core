#!/usr/bin/env bash
#
# Prepare a CI Postgres for the DB/integration test suites.
#
# Applies the SQL migration mirrors (db/migrations/*.sql) + the Alembic-only
# 004_supabase_auth DDL, then creates a NON-superuser role `appuser` and grants
# it table access. The tests connect AS appuser so Row-Level Security is actually
# enforced (a superuser/owner would bypass RLS).
#
# Required env: PGHOST, PGPORT, PGUSER (superuser), PGPASSWORD, PGDATABASE,
#               APP_DB_PASSWORD (password for the created appuser role).
#
set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root

PSQL="psql -v ON_ERROR_STOP=1 -h ${PGHOST} -p ${PGPORT} -U ${PGUSER} -d ${PGDATABASE}"

echo "→ applying SQL migrations (db/migrations/*.sql in order)..."
for f in $(ls db/migrations/*.sql | sort); do
  echo "   $f"
  $PSQL -f "$f"
done

echo "→ applying Alembic-only 004_supabase_auth DDL..."
$PSQL -c "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS auth_user_id uuid UNIQUE;"
$PSQL -c "ALTER TABLE public.users ALTER COLUMN hashed_password DROP NOT NULL;"
$PSQL -c "CREATE INDEX IF NOT EXISTS ix_users_auth_user_id ON public.users(auth_user_id);"

echo "→ creating non-superuser app role (so RLS applies)..."
$PSQL -c "DO \$\$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='appuser') THEN
    CREATE ROLE appuser LOGIN PASSWORD '${APP_DB_PASSWORD}';
  ELSE
    ALTER ROLE appuser WITH LOGIN PASSWORD '${APP_DB_PASSWORD}';
  END IF;
END \$\$;"
$PSQL -c "GRANT ALL ON SCHEMA public TO appuser;"
$PSQL -c "GRANT ALL ON ALL TABLES IN SCHEMA public TO appuser;"
$PSQL -c "GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO appuser;"

echo "✓ test DB ready"
