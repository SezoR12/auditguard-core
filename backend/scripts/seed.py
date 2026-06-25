"""Seed AuditCore with one company, one branch, and four users."""
import asyncio
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Company, Branch, User, CompanyTier, UserRole
from app.security import hash_password


SEED_USERS = [
    ("owner@auditcore.local",   "Owner123!",   "المالك",          UserRole.owner),
    ("gm@auditcore.local",      "Gm123!",      "المدير العام",     UserRole.gm),
    ("manager@auditcore.local", "Manager123!", "مدير الفرع",      UserRole.manager),
    ("auditor@auditcore.local", "Auditor123!", "المدقق",          UserRole.auditor),
]


async def main() -> None:
    async with AsyncSessionLocal() as s:
        company = (await s.execute(select(Company).where(Company.name == "شركة التقنية العراقية"))).scalar_one_or_none()
        if not company:
            company = Company(name="شركة التقنية العراقية", sector="تجارة", tier=CompanyTier.advanced)
            s.add(company)
            await s.flush()
            print(f"  + company {company.id}")

        branch = (await s.execute(select(Branch).where(Branch.company_id == company.id))).scalar_one_or_none()
        if not branch:
            branch = Branch(company_id=company.id, name="الرئيسي - بغداد", location="بغداد")
            s.add(branch)
            await s.flush()
            print(f"  + branch  {branch.id}")

        for email, password, full_name, role in SEED_USERS:
            existing = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if existing:
                print(f"  = user    {email} (exists)")
                continue
            s.add(User(
                email=email,
                hashed_password=hash_password(password),
                full_name=full_name,
                role=role,
                company_id=company.id,
                branch_id=branch.id,
                is_active=True,
            ))
            print(f"  + user    {email} [{role.value}]")

        await s.commit()
        print("seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
