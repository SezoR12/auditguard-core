"""Production seed — creates ONE company + ONE owner account, no demo data.

Reads from env (set by install.sh):
  COMPANY_NAME, COMPANY_SECTOR, OWNER_EMAIL, OWNER_PASSWORD, OWNER_FULL_NAME
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (to create the auth user)

Idempotent: re-running won't duplicate the company or owner.
"""
import asyncio
import os
import sys

import httpx
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Branch, Company, CompanyTier, User, UserRole


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


def ensure_auth_user(admin: httpx.Client, email: str, password: str, full_name: str) -> str:
    r = admin.get("/admin/users", params={"email": email})
    r.raise_for_status()
    for u in r.json().get("users", []):
        if u.get("email", "").lower() == email.lower():
            return u["id"]
    r = admin.post(
        "/admin/users",
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"full_name": full_name, "app_role": "owner"},
        },
    )
    if r.status_code >= 300:
        sys.exit(f"✗ failed to create owner auth user: {r.status_code} {r.text}")
    return r.json()["id"]


async def main() -> None:
    company_name = os.environ.get("COMPANY_NAME", "").strip()
    sector = os.environ.get("COMPANY_SECTOR", "عام").strip()
    owner_email = os.environ.get("OWNER_EMAIL", "").strip()
    owner_password = os.environ.get("OWNER_PASSWORD", "").strip()
    owner_name = os.environ.get("OWNER_FULL_NAME", "المالك").strip()

    if not company_name or not owner_email or not owner_password:
        sys.exit("✗ COMPANY_NAME, OWNER_EMAIL and OWNER_PASSWORD are required.")

    admin = _admin_client()
    auth_user_id = ensure_auth_user(admin, owner_email, owner_password, owner_name)

    async with AsyncSessionLocal() as s:
        company = (
            await s.execute(select(Company).where(Company.name == company_name))
        ).scalar_one_or_none()
        if not company:
            company = Company(name=company_name, sector=sector, tier=CompanyTier.advanced)
            s.add(company)
            await s.flush()
            print(f"  + company {company.name}")

        branch = (
            await s.execute(select(Branch).where(Branch.company_id == company.id))
        ).scalar_one_or_none()
        if not branch:
            branch = Branch(company_id=company.id, name="الفرع الرئيسي", location=sector)
            s.add(branch)
            await s.flush()

        owner = (
            await s.execute(select(User).where(User.email == owner_email))
        ).scalar_one_or_none()
        if not owner:
            s.add(
                User(
                    email=owner_email,
                    auth_user_id=auth_user_id,
                    full_name=owner_name,
                    role=UserRole.owner,
                    company_id=company.id,
                    branch_id=branch.id,
                    is_active=True,
                )
            )
            print(f"  + owner {owner_email}")
        elif str(owner.auth_user_id) != str(auth_user_id):
            owner.auth_user_id = auth_user_id
            print(f"  ~ owner {owner_email} (linked auth)")

        await s.commit()
    print("production seed complete (owner only, no demo data).")


if __name__ == "__main__":
    asyncio.run(main())
