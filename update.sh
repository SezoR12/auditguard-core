#!/usr/bin/env bash
#
# AuditCore — maintenance update with backup + health-gated rollback.
#   ./update.sh            # pull/rebuild, migrate, health-check, rollback on failure
#
# Strategy for a single box: snapshot current image IDs, back up, rebuild &
# recreate the backend/worker/beat, run migrations, then verify /health. If the
# health check fails, roll back to the snapshotted images.
#
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
# shellcheck disable=SC1091
[ -f .env ] && { set -a; source .env; set +a; }

bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*"; }

wait_health() {
  for _ in $(seq 1 "${1:-30}"); do
    if curl -fsS --max-time 5 http://localhost:8000/health 2>/dev/null | grep -q '"status"[: ]*"ok"'; then
      return 0
    fi
    sleep 4
  done
  return 1
}

# ---------------------------------------------------------------------------
# 1. Pre-update backup
# ---------------------------------------------------------------------------
bold "→ Pre-update backup..."
if [ -x ./backup.sh ]; then
  ./backup.sh || red "  backup reported issues (continuing — review logs)"
else
  red "  backup.sh not found/executable; skipping (NOT recommended)"
fi

# ---------------------------------------------------------------------------
# 2. Snapshot current backend image for rollback
# ---------------------------------------------------------------------------
bold "→ Snapshotting current images for rollback..."
PREV_BACKEND_IMG=$(docker compose images -q backend 2>/dev/null || true)
docker image tag "$(docker compose images -q backend 2>/dev/null)" auditcore_backend:rollback 2>/dev/null || true
green "  snapshot: ${PREV_BACKEND_IMG:-none}"

# ---------------------------------------------------------------------------
# 3. Pull latest source images (from registry if configured) + rebuild
# ---------------------------------------------------------------------------
if [ -n "${REGISTRY_URL:-}" ]; then
  bold "→ Pulling images from ${REGISTRY_URL} (VPN/registry)..."
  docker compose pull || red "  pull failed; will rebuild locally"
fi

bold "→ Rebuilding & recreating app services (minimal downtime)..."
docker compose up -d --build --no-deps backend worker beat

# ---------------------------------------------------------------------------
# 4. Migrations
# ---------------------------------------------------------------------------
bold "→ Running migrations..."
docker compose exec -T backend alembic upgrade head || {
  red "✗ migration failed — rolling back"; ROLLBACK=1;
}

# ---------------------------------------------------------------------------
# 5. Health gate
# ---------------------------------------------------------------------------
if [ "${ROLLBACK:-0}" != "1" ]; then
  bold "→ Verifying health..."
  if wait_health 30; then
    green "✓ Update successful — system healthy."
    exit 0
  fi
  red "✗ Health check failed after update."
  ROLLBACK=1
fi

# ---------------------------------------------------------------------------
# 6. Rollback
# ---------------------------------------------------------------------------
if [ "${ROLLBACK:-0}" = "1" ]; then
  red "→ Rolling back to previous backend image..."
  if docker image inspect auditcore_backend:rollback >/dev/null 2>&1; then
    # Recreate using the snapshot tag.
    docker tag auditcore_backend:rollback "$(docker compose config --images | grep -i backend | head -1 || echo auditcore-backend)" 2>/dev/null || true
    docker compose up -d --no-deps backend worker beat
    if wait_health 30; then
      red "  Rolled back. System healthy on the previous version."
      exit 2
    fi
  fi
  red "  Rollback could not confirm health. Manual intervention required."
  red "  Restore from /data/backups (see TROUBLESHOOTING.md)."
  exit 3
fi
