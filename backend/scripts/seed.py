"""Seed AuditCore: company, branch, and four users in BOTH Supabase Auth
(`auth.users`) and the app profile table (`public.users`), linked via
`auth_user_id`.

Requires env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (admin API).
Idempotent — safe to re-run.
"""
import asyncio
import os
import sys
import httpx
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Company, Branch, User, CompanyTier, UserRole


SEED_USERS = [
    ("owner@auditcore.local",   "Owner123!",   "المالك",          UserRole.owner),
    ("gm@auditcore.local",      "Gm123!",      "المدير العام",     UserRole.gm),
    ("manager@auditcore.local", "Manager123!", "مدير الفرع",      UserRole.manager),
    ("auditor@auditcore.local", "Auditor123!", "المدقق",          UserRole.auditor),
]


def _admin_client() -> httpx.Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("✗ SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.")
    return httpx.Client(
        base_url=f"{url.rstrip('/')}/auth/v1",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=30.0,
    )


def ensure_auth_user(admin: httpx.Client, email: str, password: str, full_name: str, role: str) -> str:
    """Create or fetch the auth.users row; return its UUID."""
    # Try to find existing.
    r = admin.get("/admin/users", params={"email": email})
    r.raise_for_status()
    for u in r.json().get("users", []):
        if u.get("email", "").lower() == email.lower():
            return u["id"]

    # Create new (email pre-confirmed so seed users can log in immediately).
    r = admin.post(
        "/admin/users",
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"full_name": full_name, "app_role": role},
        },
    )
    if r.status_code >= 300:
        sys.exit(f"✗ failed to create auth user {email}: {r.status_code} {r.text}")
    return r.json()["id"]


async def main() -> None:
    admin = _admin_client()

    async with AsyncSessionLocal() as s:
        company = (await s.execute(
            select(Company).where(Company.name == "شركة التقنية العراقية")
        )).scalar_one_or_none()
        if not company:
            company = Company(name="شركة التقنية العراقية", sector="تجارة", tier=CompanyTier.advanced)
            s.add(company)
            await s.flush()
            print(f"  + company {company.id}")

        branch = (await s.execute(
            select(Branch).where(Branch.company_id == company.id)
        )).scalar_one_or_none()
        if not branch:
            branch = Branch(company_id=company.id, name="الرئيسي - بغداد", location="بغداد")
            s.add(branch)
            await s.flush()
            print(f"  + branch  {branch.id}")

        for email, password, full_name, role in SEED_USERS:
            auth_user_id = ensure_auth_user(admin, email, password, full_name, role.value)
            existing = (await s.execute(
                select(User).where(User.email == email)
            )).scalar_one_or_none()
            if existing:
                if str(existing.auth_user_id) != str(auth_user_id):
                    existing.auth_user_id = auth_user_id
                    print(f"  ~ user    {email} (linked auth_user_id)")
                else:
                    print(f"  = user    {email} (exists)")
                continue
            s.add(User(
                email=email,
                auth_user_id=auth_user_id,
                full_name=full_name,
                role=role,
                company_id=company.id,
                branch_id=branch.id,
                is_active=True,
            ))
            print(f"  + user    {email} [{role.value}]  auth={auth_user_id}")

        await s.commit()
        print("seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
