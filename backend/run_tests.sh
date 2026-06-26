#!/usr/bin/env bash
#
# Run all AuditCore backend test suites.
#
# Pure-logic suites run with dummy env. DB/integration suites need a reachable
# Postgres (as a NON-superuser role, so RLS applies) and Redis; they are run
# only when RUN_DB_TESTS=1 and the connection env vars are set.
#
# Local quick run (pure-logic only):
#   ./run_tests.sh
# Full run (CI / with services):
#   RUN_DB_TESTS=1 ./run_tests.sh
#
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD"

PY="${PYTHON:-python}"
FAILED=0

# Dummy env for pure-logic suites (overridden by real env when present).
export SUPABASE_DB_HOST="${SUPABASE_DB_HOST:-x}"
export SUPABASE_DB_USER="${SUPABASE_DB_USER:-x}"
export SUPABASE_DB_PASSWORD="${SUPABASE_DB_PASSWORD:-x}"
export SECRET_KEY="${SECRET_KEY:-testsecret}"
export ENCRYPTION_MASTER_KEY="${ENCRYPTION_MASTER_KEY:-testkey}"
export SUPABASE_URL="${SUPABASE_URL:-https://test.supabase.co}"
export SUPABASE_JWT_SECRET="${SUPABASE_JWT_SECRET:-test-secret}"
export SUPABASE_JWT_AUDIENCE="${SUPABASE_JWT_AUDIENCE:-authenticated}"
# Writable storage root for export/upload tests (CI / sandbox has no /data).
export STORAGE_ROOT="${STORAGE_ROOT:-$(mktemp -d 2>/dev/null || echo /tmp/auditcore_test_data)}"
mkdir -p "$STORAGE_ROOT" 2>/dev/null || true

PURE=(
  tests/test_phase2_ingestion.py
  tests/test_phase3_logic.py
  tests/test_phase4_sla.py
  tests/test_phase5_ledger.py
  tests/test_phase6_ai.py
  tests/test_phase8_notify.py
  tests/test_phase9_exports.py
  tests/test_phase11_templates.py
  tests/test_phase12_sector_metrics.py
)

DB=(
  tests/test_phase6b_auth_flow.py
  tests/test_phase7_dashboard.py
  tests/test_phase8_notify_db.py
  tests/test_phase9_exports_db.py
  tests/test_phase11_templates_db.py
  tests/test_phase12_sector_metrics_db.py
)

run() {
  echo "──────────────────────────────────────────"
  echo "▶ $1"
  if "$PY" "$1"; then
    echo "✓ $1"
  else
    echo "✗ $1"
    FAILED=1
  fi
}

echo "=== pure-logic suites ==="
for t in "${PURE[@]}"; do run "$t"; done

if [ "${RUN_DB_TESTS:-0}" = "1" ]; then
  echo ""
  echo "=== DB / integration suites ==="
  for t in "${DB[@]}"; do run "$t"; done
else
  echo ""
  echo "(skipping DB/integration suites — set RUN_DB_TESTS=1 with Postgres+Redis to include them)"
fi

echo "──────────────────────────────────────────"
[ "$FAILED" = "0" ] && echo "ALL SUITES PASSED" || echo "SOME SUITES FAILED"
exit $FAILED
