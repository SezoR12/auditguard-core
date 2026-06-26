# AuditCore — Troubleshooting

Quick fixes for the most common on-site issues. Run all commands from
`/opt/auditcore`.

---

## Containers / general

**See what's running**
```bash
docker compose ps
docker compose logs -f backend       # or: worker, beat, frontend, baileys-bridge, redis
```

**Restart everything**
```bash
docker compose restart
# full rebuild if needed:
docker compose up -d --build
```

**Deep health check**
```bash
curl http://localhost:8000/health
```
`"status":"ok"` is good. `"degraded"` shows which dependency (database/redis)
is failing in the `checks` object.

---

## "Failed to fetch" / cannot log in

1. Is the backend up? `curl http://localhost:8000/health`
2. Is the frontend pointed at the right API? Check `VITE_AUDITCORE_API_URL` in
   `.env`. In a browser preview it must be an HTTPS URL reachable from the
   browser (not `localhost`).
3. Is the Supabase project reachable from the box?
   ```bash
   docker compose exec backend python -c "import asyncio;from app.database import engine;from sqlalchemy import text;\
   asyncio.run(engine.connect().__aenter__())"
   ```

---

## Forgot Owner password

Passwords live in **Supabase Auth**, not the app DB. Reset via the Supabase
admin API (service role key is in `.env`):
```bash
docker compose exec backend python - <<'PY'
import os, httpx
url=os.environ["SUPABASE_URL"].rstrip("/"); key=os.environ["SUPABASE_SERVICE_ROLE_KEY"]
c=httpx.Client(base_url=f"{url}/auth/v1", headers={"apikey":key,"Authorization":f"Bearer {key}"})
# find the user id by email
u=c.get("/admin/users", params={"email":"owner@example.com"}).json()["users"][0]
c.put(f"/admin/users/{u['id']}", json={"password":"NewStrongPass!123"})
print("password reset for", u["email"])
PY
```

---

## Disk full

```bash
df -h
# Old backups rotate automatically, but you can prune Docker too:
docker system prune -f
# Inspect backup sizes (inside the data volume):
docker compose exec backend du -sh /data/* 2>/dev/null
```
The healthcheck alerts the Owner on WhatsApp when disk usage exceeds 80%.

---

## WhatsApp disconnected / not sending

1. Check the bridge: `docker compose logs -f baileys-bridge`
2. If you see a **QR code**, the session dropped — re-link: WhatsApp →
   Linked Devices → scan.
3. Messages sent while disconnected are **queued in Redis** and auto-retried
   every 5 minutes. Inspect the queue length:
   ```bash
   docker compose exec redis redis-cli LLEN whatsapp:queue
   ```
4. The WhatsApp session is stored in the `/data/whatsapp_auth` volume and
   survives restarts; you should only need to scan once.

---

## OCR not processing uploads

1. Is the worker running? `docker compose ps worker`
2. Logs: `docker compose logs -f worker`
3. Tesseract Arabic pack is built into the backend image; if OCR text looks
   wrong, the source scan quality is usually the cause (low confidence → fields
   flagged red for the auditor to correct, by design).

---

## Restore from backup

Backups are in the `/data/backups` volume, AES-256 encrypted with
`ENCRYPTION_MASTER_KEY` from `.env`.

```bash
# Decrypt + restore a DB dump (DANGEROUS: overwrites current data)
KEY=$(grep ENCRYPTION_MASTER_KEY .env | cut -d= -f2)
docker compose exec -T backend sh -c '
  openssl enc -d -aes-256-cbc -pbkdf2 -pass pass:'"$KEY"' \
    -in /data/backups/db_<TIMESTAMP>.sql.gz.enc | gunzip |
  PGPASSWORD="$SUPABASE_DB_PASSWORD" psql -h "$SUPABASE_DB_HOST" -p "${SUPABASE_DB_PORT:-6543}" \
    -U "$SUPABASE_DB_USER" -d "${SUPABASE_DB_NAME:-postgres}"
'
```

---

## Update went wrong

`update.sh` automatically rolls back to the previous backend image if the
post-update health check fails (exit code 2 = rolled back successfully). If it
exits 3, restore from the pre-update backup (see "Restore from backup") and
contact the App Owner.
