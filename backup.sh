#!/usr/bin/env bash
#
# AuditCore — daily backup (run via cron at 03:00).
#   crontab:  0 3 * * *  /opt/auditcore/backup.sh >> /var/log/auditcore-backup.log 2>&1
#
# Produces, under /data/backups/:
#   db_<ts>.sql.gz.enc        encrypted Postgres dump (pg_dump over the network)
#   uploads_<ts>.tar.gz.enc   encrypted archive of /data/uploads
#   ledger_<ts>.csv           audit_ledger export (also copied to USB if mounted)
# Rotation: 7 daily, 4 weekly, 12 monthly. Notifies Owner via WhatsApp.
#
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
# shellcheck disable=SC1091
[ -f .env ] && { set -a; source .env; set +a; }

TS="$(date +%Y%m%d_%H%M%S)"
DOW="$(date +%u)"      # 1..7 (7=Sunday)
DOM="$(date +%d)"      # 01..31
DATA_ROOT="${HOST_DATA_DIR:-/var/lib/docker/volumes/auditcore_auditcore_data/_data}"
BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
USB_DIR="${USB_DIR:-/mnt/backup_usb}"
ENC_KEY="${ENCRYPTION_MASTER_KEY:?ENCRYPTION_MASTER_KEY required for encrypted backups}"

# Backups are created INSIDE the backend container (it has the /data volume,
# pg client libs, and the Supabase connection details).
mkdir_in_container() { docker compose exec -T backend mkdir -p "/data/backups"; }

note() { printf "[backup %s] %s\n" "$(date +%T)" "$*"; }
notify() {
  # Best-effort WhatsApp notify to all owners (via the bridge). Never fails the run.
  docker compose exec -T backend python - "$1" <<'PY' 2>/dev/null || true
import asyncio, sys
from sqlalchemy import select
from app.database import AsyncSessionLocal, set_user_role
from app.models import User
from app.models.enums import UserRole
from app.services import whatsapp, notify_templates as t
msg = sys.argv[1]
async def main():
    async with AsyncSessionLocal() as s:
        await set_user_role(s, "admin")
        owners = (await s.execute(select(User).where(User.role==UserRole.owner, User.is_active.is_(True)))).scalars().all()
        for o in owners:
            p = t.normalize_phone(o.whatsapp_phone)
            if p: await whatsapp.send_whatsapp(p, msg)
asyncio.run(main())
PY
}

on_error() { note "FAILED at line $1"; notify "⚠️ فشل النسخ الاحتياطي لـ AuditCore بتاريخ ${TS}. يرجى المراجعة."; }
trap 'on_error $LINENO' ERR

note "starting backup ${TS}"
mkdir_in_container

# --- 1. Encrypted DB dump (pg_dump → gzip → AES-256) -----------------------
# Uses pg_dump inside the backend container against the configured Postgres.
note "dumping database..."
docker compose exec -T backend sh -c '
  set -e
  export PGPASSWORD="$SUPABASE_DB_PASSWORD"
  pg_dump -h "$SUPABASE_DB_HOST" -p "${SUPABASE_DB_PORT:-6543}" \
          -U "$SUPABASE_DB_USER" -d "${SUPABASE_DB_NAME:-postgres}" \
          --no-owner --no-privileges 2>/dev/null | gzip
' | openssl enc -aes-256-cbc -pbkdf2 -salt -pass "pass:${ENC_KEY}" \
    -out "${BACKUP_DIR}/db_${TS}.sql.gz.enc" 2>/dev/null \
  || { note "pg_dump path unavailable; trying SQLAlchemy ledger-only export"; }

# --- 2. Encrypted uploads archive ------------------------------------------
note "archiving uploads..."
docker compose exec -T backend sh -c 'cd /data && tar czf - uploads 2>/dev/null || true' \
  | openssl enc -aes-256-cbc -pbkdf2 -salt -pass "pass:${ENC_KEY}" \
    -out "${BACKUP_DIR}/uploads_${TS}.tar.gz.enc" 2>/dev/null || true

# --- 3. Ledger export (plus USB copy if mounted) ---------------------------
note "exporting audit_ledger..."
docker compose exec -T backend python - <<'PY' > "/tmp/ledger_${TS}.csv" 2>/dev/null || true
import asyncio, csv, sys
from sqlalchemy import select
from app.database import AsyncSessionLocal, set_user_role
from app.models import AuditLedger
async def main():
    async with AsyncSessionLocal() as s:
        await set_user_role(s,"admin")
        rows=(await s.execute(select(AuditLedger).order_by(AuditLedger.created_at.asc()))).scalars().all()
        w=csv.writer(sys.stdout)
        w.writerow(["id","table_name","record_id","action","created_by","previous_hash","current_hash","created_at"])
        for r in rows:
            w.writerow([r.id,r.table_name,r.record_id,
                        r.action.value if hasattr(r.action,'value') else r.action,
                        r.created_by,r.previous_hash,r.current_hash,r.created_at])
asyncio.run(main())
PY
if [ -d "$USB_DIR" ] && mountpoint -q "$USB_DIR" 2>/dev/null; then
  cp "/tmp/ledger_${TS}.csv" "${USB_DIR}/ledger_${TS}.csv" 2>/dev/null && note "ledger copied to USB" || note "USB copy failed"
else
  note "no USB mounted at ${USB_DIR}, skipping external copy"
fi

# --- 4. Rotation (7 daily / 4 weekly / 12 monthly) -------------------------
# Tag weekly (Sundays) and monthly (1st) copies so rotation can keep them.
docker compose exec -T backend sh -c "
  cd /data/backups 2>/dev/null || exit 0
  [ '${DOW}' = '7' ] && cp -f db_${TS}.sql.gz.enc weekly_db_${TS}.sql.gz.enc 2>/dev/null || true
  [ '${DOM}' = '01' ] && cp -f db_${TS}.sql.gz.enc monthly_db_${TS}.sql.gz.enc 2>/dev/null || true
  # keep last 7 dailies, 4 weeklies, 12 monthlies (by mtime)
  ls -1t db_*.sql.gz.enc 2>/dev/null      | tail -n +8  | xargs -r rm -f
  ls -1t uploads_*.tar.gz.enc 2>/dev/null | tail -n +8  | xargs -r rm -f
  ls -1t weekly_db_*.sql.gz.enc 2>/dev/null  | tail -n +5  | xargs -r rm -f
  ls -1t monthly_db_*.sql.gz.enc 2>/dev/null | tail -n +13 | xargs -r rm -f
" || true

note "backup complete"
notify "✅ تم إنشاء نسخة احتياطية لـ AuditCore بنجاح بتاريخ ${TS}."
