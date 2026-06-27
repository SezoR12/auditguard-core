#!/usr/bin/env bash
set -euo pipefail

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
red() { printf "\033[31m%s\033[0m\n" "$*"; }

command -v docker >/dev/null 2>&1 || { red "Docker غير مثبت"; exit 1; }
docker compose version >/dev/null 2>&1 || { red "Docker Compose v2 غير مثبت"; exit 1; }

if [ ! -f .env ]; then
  red "ملف .env غير موجود. انسخه من .env.example ثم عبّئ متغيرات Supabase أولاً."
  exit 1
fi

# shellcheck disable=SC1091
set -a; source .env; set +a

required=(
  SUPABASE_DB_HOST
  SUPABASE_DB_PORT
  SUPABASE_DB_NAME
  SUPABASE_DB_USER
  SUPABASE_DB_PASSWORD
  SUPABASE_URL
  SUPABASE_JWT_SECRET
  SUPABASE_SERVICE_ROLE_KEY
  VITE_AUDITCORE_SUPABASE_URL
  VITE_AUDITCORE_SUPABASE_ANON_KEY
)

for key in "${required[@]}"; do
  if [ -z "${!key:-}" ] || [[ "${!key}" == replace-* ]]; then
    red "المتغير ${key} غير مضبوط في .env"
    exit 1
  fi
done

bold "→ تشغيل redis + backend للمعاينة"
docker compose up -d redis backend

bold "→ انتظار جاهزية backend"
for i in {1..45}; do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
  red "فشل تشغيل FastAPI على http://localhost:8000"
  exit 1
fi

bold "→ تشغيل migrations"
docker compose exec -T backend alembic upgrade head

bold "→ تطبيق سياسات RLS"
docker compose exec -T backend python scripts/apply_rls.py

bold "→ تنفيذ seed للمستخدمين التجريبيين"
docker compose exec -T backend python scripts/seed.py

green "تم تشغيل FastAPI محليًا للمعاينة."
green "Backend: http://localhost:8000/docs"
green "يمكنك الآن تجربة تسجيل الدخول بحيث تعمل api.me() بدون fallback."
