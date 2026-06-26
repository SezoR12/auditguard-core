# AuditCore — Deployment Guide (Technician)

This guide is written for an on-site technician (no programming required) to
install AuditCore on a Smart Box (a small server) running **Ubuntu 22.04**.

Target: **from a fresh server to a working login page in under 30 minutes.**

---

## 1. What you need before you start

- A server/PC with **Ubuntu 22.04**, **≥ 4 GB RAM**, **≥ 100 GB free disk**.
- Internet access during installation.
- The **Supabase project details** (from the customer's account or App Owner):
  - Database host, user, password
  - Project URL (`https://<ref>.supabase.co`)
  - JWT Secret, Service Role key, Anon (publishable) key
- The customer's **company name, sector, and the Owner's email**.

> **Architecture note.** Today AuditCore uses **Supabase** for the database and
> login. The app itself (API, background workers, Redis, WhatsApp bridge) runs
> on the box. For a **fully offline / air-gapped** box with a *local* database,
> see "Appendix: Fully on-prem Postgres" at the end.

---

## 2. Install Docker (one time)

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"   # then log out and back in
```

Verify:
```bash
docker --version
docker compose version
```

---

## 3. Get the AuditCore code

```bash
sudo mkdir -p /opt/auditcore && sudo chown "$USER" /opt/auditcore
git clone <REPO_URL> /opt/auditcore
cd /opt/auditcore
```

---

## 4. Run the installer

```bash
./install.sh
```

The installer will:
1. Check Docker, RAM, and disk.
2. Ask for the company name, sector, Owner email/name/password (auto-generates a
   strong password if you leave it blank).
3. Ask for the Supabase connection details.
4. Generate a secure `.env` (random `ENCRYPTION_MASTER_KEY`, `JWT_SECRET`, etc.).
5. Build and start all containers.
6. Run database migrations + RLS policies.
7. Seed **only the Owner account** (no demo data).
8. Print the **login URL and Owner credentials**.

**Write down the credentials it prints.** Ask the Owner to change the password
after the first login.

---

## 5. Link WhatsApp (one time)

Alerts and the daily digest go out over WhatsApp via the Baileys bridge.

```bash
docker compose logs -f baileys-bridge
```
A **QR code** appears in the logs. On the Owner's phone:
**WhatsApp → Settings → Linked Devices → Link a device →** scan the QR.

Then set the Owner's WhatsApp number so they receive alerts (replace the number):
```bash
docker compose exec backend python - <<'PY'
import asyncio
from sqlalchemy import update
from app.database import AsyncSessionLocal, set_user_role
from app.models import User
async def main():
    async with AsyncSessionLocal() as s:
        await set_user_role(s,"admin")
        await s.execute(update(User).where(User.role=="owner").values(whatsapp_phone="9647XXXXXXXXX"))
        await s.commit()
asyncio.run(main())
PY
```

---

## 6. Verify it's working

- Open **http://<server-ip>:5173/login** and log in as the Owner.
- Check health: **http://<server-ip>:8000/health** → should say `"status":"ok"`.

---

## 7. Schedule backups & monitoring (recommended)

```bash
crontab -e
```
Add:
```
0 3 * * *   /opt/auditcore/backup.sh      >> /var/log/auditcore-backup.log 2>&1
*/5 * * * * /opt/auditcore/healthcheck.sh >> /var/log/auditcore-health.log 2>&1
```

Optional: plug a USB drive and mount it at `/mnt/backup_usb` — the backup will
copy the audit ledger there automatically.

---

## 8. Updating later

```bash
cd /opt/auditcore
git pull          # or pull new images if using a registry
./update.sh       # backs up, updates, health-checks, auto-rolls-back on failure
```

---

## Appendix: Fully on-prem Postgres (air-gapped)

To remove the Supabase dependency and run the database **on the box**:

1. Add a `postgres:15` service to `docker-compose.yml` with a `postgres_data`
   volume and `POSTGRES_PASSWORD` from `.env` (do **not** publish port 5432).
2. Point `SUPABASE_DB_HOST=postgres`, `SUPABASE_DB_PORT=5432`,
   `SUPABASE_DB_USER=auditcore_app` (a non-superuser role — required so RLS is
   enforced), and set its password.
3. Replace Supabase Auth with the Phase-1 local JWT auth, or run a self-hosted
   GoTrue. (Contact the App Owner for the air-gapped bundle.)
4. `backup.sh` already uses `pg_dump`; point it at the local service.

This keeps the entire system inside the customer's network with no external
calls except optional WhatsApp.
