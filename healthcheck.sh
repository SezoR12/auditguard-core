#!/usr/bin/env bash
#
# AuditCore — health monitor (run via cron every 5 min).
#   */5 * * * *  /opt/auditcore/healthcheck.sh >> /var/log/auditcore-health.log 2>&1
#
# Checks: containers running, disk > 20% free, RAM < 90% used, /health endpoint,
# UPS status (if `upsc`/apcaccess available). Sends a critical WhatsApp alert to
# owners (and APP_OWNER_PHONE if set) on any failure.
#
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
# shellcheck disable=SC1091
[ -f .env ] && { set -a; source .env; set +a; }

PROBLEMS=()
note() { printf "[health %s] %s\n" "$(date +%T)" "$*"; }

# --- containers ------------------------------------------------------------
EXPECTED=(backend worker beat redis frontend baileys-bridge)
for svc in "${EXPECTED[@]}"; do
  state=$(docker compose ps -q "$svc" 2>/dev/null)
  if [ -z "$state" ]; then
    PROBLEMS+=("الحاوية ${svc} غير قيد التشغيل")
    continue
  fi
  running=$(docker inspect -f '{{.State.Running}}' "$state" 2>/dev/null || echo "false")
  [ "$running" = "true" ] || PROBLEMS+=("الحاوية ${svc} متوقفة")
done

# --- disk (> 20% free) -----------------------------------------------------
USE_PCT=$(df --output=pcent / 2>/dev/null | tail -1 | tr -dc '0-9')
if [ -n "${USE_PCT:-}" ] && [ "$USE_PCT" -gt 80 ]; then
  PROBLEMS+=("مساحة القرص منخفضة: ${USE_PCT}% مستخدمة")
fi

# --- RAM (< 90% used) ------------------------------------------------------
if [ -r /proc/meminfo ]; then
  TOTAL=$(awk '/MemTotal/{print $2}' /proc/meminfo)
  AVAIL=$(awk '/MemAvailable/{print $2}' /proc/meminfo)
  if [ -n "$TOTAL" ] && [ "$TOTAL" -gt 0 ]; then
    USED_PCT=$(( (TOTAL - AVAIL) * 100 / TOTAL ))
    [ "$USED_PCT" -ge 90 ] && PROBLEMS+=("استخدام الذاكرة مرتفع: ${USED_PCT}%")
  fi
fi

# --- /health endpoint ------------------------------------------------------
HEALTH=$(curl -fsS --max-time 10 "http://localhost:8000/health" 2>/dev/null || echo "")
if ! printf '%s' "$HEALTH" | grep -q '"status"[: ]*"ok"'; then
  PROBLEMS+=("نقطة الفحص /health غير سليمة")
fi

# --- UPS (optional) --------------------------------------------------------
if command -v upsc >/dev/null 2>&1; then
  ups=$(upsc "${UPS_NAME:-ups}" ups.status 2>/dev/null || echo "")
  case "$ups" in
    *OB*) PROBLEMS+=("UPS يعمل على البطارية (انقطاع التيار)") ;;
    *LB*) PROBLEMS+=("بطارية UPS منخفضة") ;;
  esac
fi

# --- report ----------------------------------------------------------------
if [ ${#PROBLEMS[@]} -eq 0 ]; then
  note "all checks passed"
  exit 0
fi

note "PROBLEMS: ${PROBLEMS[*]}"
MSG="🚨 تنبيه صيانة AuditCore"$'\n'"$(printf '• %s\n' "${PROBLEMS[@]}")"

# Notify owners via WhatsApp through the backend (best-effort), plus APP_OWNER_PHONE.
docker compose exec -T -e APP_OWNER_PHONE="${APP_OWNER_PHONE:-}" backend python - "$MSG" <<'PY' 2>/dev/null || true
import asyncio, os, sys
from sqlalchemy import select
from app.database import AsyncSessionLocal, set_user_role
from app.models import User
from app.models.enums import UserRole
from app.services import whatsapp, notify_templates as t
msg=sys.argv[1]
async def main():
    targets=[]
    async with AsyncSessionLocal() as s:
        await set_user_role(s,"admin")
        owners=(await s.execute(select(User).where(User.role==UserRole.owner, User.is_active.is_(True)))).scalars().all()
        targets=[t.normalize_phone(o.whatsapp_phone) for o in owners]
    extra=t.normalize_phone(os.environ.get("APP_OWNER_PHONE",""))
    if extra: targets.append(extra)
    for p in [x for x in targets if x]:
        await whatsapp.send_whatsapp(p, msg)  # queues if bridge offline
asyncio.run(main())
PY

exit 1
