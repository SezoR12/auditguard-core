import os, sys, os.path; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import uuid as _uuid_sfx
_EMAIL_SFX = _uuid_sfx.uuid4().hex[:8]
def _em(addr):
    user, _, dom = addr.partition('@')
    return f'{user}+{_EMAIL_SFX}@{dom}'
import asyncio, uuid, time
from jose import jwt
import httpx
from httpx import ASGITransport
from sqlalchemy import select, func, text
from app.database import AsyncSessionLocal, engine, set_user_role, set_user_context
from app.models import Company, Branch, User, AuditTask, Document, DocumentCertification, AuditLedger
from app.models.enums import (
    CompanyTier, UserRole, TaskType, TaskStatus,
    FileType, DocCategory, DocStatus, LedgerAction,
)
from app.config import settings
from app.main import app

P = []; F = []
def ck(n, c): (P if c else F).append(n); print(("PASS " if c else "FAIL ") + n)


def mint(sub, email, exp_delta=3600):
    return jwt.encode(
        {"sub": sub, "email": email, "aud": "authenticated", "role": "authenticated",
         "iat": int(time.time()), "exp": int(time.time()) + exp_delta},
        settings.SUPABASE_JWT_SECRET, algorithm="HS256",
    )


# Auth (Supabase sub) ids per seeded role.
AUTH = {r: str(uuid.uuid4()) for r in ("owner", "gm", "manager", "auditor")}
# A second auditor in a DIFFERENT branch, and one in a DIFFERENT company.
AUTH_AUD2 = str(uuid.uuid4())
AUTH_OWNER_B = str(uuid.uuid4())

IDS = {}  # role -> public.users.id


async def seed():
    async with AsyncSessionLocal() as s:
        await set_user_role(s, "admin")
        # Company A with two branches.
        ca = Company(name="شركة أ", sector="general", tier=CompanyTier.advanced); s.add(ca); await s.flush()
        b1 = Branch(company_id=ca.id, name="فرع ١", location="بغداد"); s.add(b1)
        b2 = Branch(company_id=ca.id, name="فرع ٢", location="البصرة"); s.add(b2); await s.flush()
        # Company B (isolation check).
        cb = Company(name="شركة ب", sector="general", tier=CompanyTier.advanced); s.add(cb); await s.flush()
        bb = Branch(company_id=cb.id, name="فرع ب", location="أربيل"); s.add(bb); await s.flush()

        owner = User(email=_em("owner@auditcore.local"), full_name="المالك", role=UserRole.owner,
                     company_id=ca.id, is_active=True, auth_user_id=uuid.UUID(AUTH["owner"]))
        gm = User(email=_em("gm@auditcore.local"), full_name="المدير العام", role=UserRole.gm,
                  company_id=ca.id, is_active=True, auth_user_id=uuid.UUID(AUTH["gm"]))
        manager = User(email=_em("manager@auditcore.local"), full_name="المدير", role=UserRole.manager,
                       company_id=ca.id, branch_id=b1.id, is_active=True, auth_user_id=uuid.UUID(AUTH["manager"]))
        auditor = User(email=_em("auditor@auditcore.local"), full_name="المدقق", role=UserRole.auditor,
                       company_id=ca.id, branch_id=b1.id, is_active=True, auth_user_id=uuid.UUID(AUTH["auditor"]))
        auditor2 = User(email=_em("auditor2@auditcore.local"), full_name="مدقق ٢", role=UserRole.auditor,
                        company_id=ca.id, branch_id=b2.id, is_active=True, auth_user_id=uuid.UUID(AUTH_AUD2))
        owner_b = User(email=_em("ownerb@auditcore.local"), full_name="مالك ب", role=UserRole.owner,
                       company_id=cb.id, is_active=True, auth_user_id=uuid.UUID(AUTH_OWNER_B))
        s.add_all([owner, gm, manager, auditor, auditor2, owner_b]); await s.flush()
        for k, u in (("owner", owner), ("gm", gm), ("manager", manager),
                     ("auditor", auditor), ("auditor2", auditor2), ("owner_b", owner_b)):
            IDS[k] = u.id

        # Tasks: one per auditor (branch1 & branch2) in company A.
        s.add(AuditTask(auditor_id=auditor.id, title="مهمة المدقق ١", task_type=TaskType.document_review,
                        status=TaskStatus.pending))
        s.add(AuditTask(auditor_id=auditor2.id, title="مهمة المدقق ٢", task_type=TaskType.field_visit,
                        status=TaskStatus.pending))

        # Documents: one in company A (uploaded by auditor), one in company B.
        doc_a = Document(file_path="a", original_filename="a.pdf", file_type=FileType.pdf,
                         doc_category=DocCategory.invoice, status=DocStatus.certified,
                         uploaded_by=auditor.id, company_id=ca.id, branch_id=b1.id)
        doc_b = Document(file_path="b", original_filename="b.pdf", file_type=FileType.pdf,
                         doc_category=DocCategory.invoice, status=DocStatus.certified,
                         uploaded_by=owner_b.id, company_id=cb.id)
        s.add_all([doc_a, doc_b]); await s.flush()
        IDS["doc_a"] = doc_a.id
        IDS["doc_b"] = doc_b.id

        # Certification on company-A doc by the auditor.
        s.add(DocumentCertification(document_id=doc_a.id, auditor_id=auditor.id, is_valid=True))
        await s.commit()


# (role, path, expect_status) — each role hits its OWN dashboard (200) and a
# disallowed endpoint (403 with Arabic detail).
DASH = {"owner": "/owner/dashboard", "gm": "/gm/dashboard",
        "manager": "/manager/dashboard", "auditor": "/auditor/dashboard"}
# A representative disallowed endpoint per role.
DISALLOWED = {
    "owner": "/auditor/dashboard",       # owner cannot pose as auditor scope page
    "gm": "/auditor/dashboard",
    "manager": "/owner/dashboard",       # manager blocked from owner dashboard
    "auditor": "/owner/dashboard",       # auditor zero-knowledge of owner layer
}


async def main():
    await seed()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Each role reaches ITS OWN dashboard (200).
        for role, path in DASH.items():
            h = {"Authorization": f"Bearer {mint(AUTH[role], _em(role + '@auditcore.local'))}"}
            r = await ac.get(path, headers=h)
            ck(f"{role} -> {path} 200", r.status_code == 200)

        # 2. Each role is blocked (403 + Arabic) from a disallowed endpoint.
        for role, path in DISALLOWED.items():
            h = {"Authorization": f"Bearer {mint(AUTH[role], _em(role + '@auditcore.local'))}"}
            r = await ac.get(path, headers=h)
            ok = r.status_code == 403
            ck(f"{role} -> {path} 403", ok)
            if ok:
                detail = r.json().get("detail", "")
                ck(f"{role} 403 detail is Arabic", "صلاحية" in detail)

        # 3. /auth/me resolves the right role for each.
        for role in DASH:
            h = {"Authorization": f"Bearer {mint(AUTH[role], _em(role + '@auditcore.local'))}"}
            r = await ac.get("/auth/me", headers=h)
            ck(f"{role} /auth/me role={role}", r.status_code == 200 and r.json().get("role") == role)

        # 4. No token -> 401 (Arabic).
        r = await ac.get("/auth/me")
        ck("no token -> 401", r.status_code == 401)

        # 5. Auditor sees only their OWN assigned tasks via the API.
        ah = {"Authorization": f"Bearer {mint(AUTH['auditor'], _em('auditor@auditcore.local'))}"}
        # generate-daily is admin-gated -> auditor 403 (role gate) — sanity.
        r = await ac.get("/tasks/my-tasks", headers=ah)
        ck("auditor /tasks/my-tasks 200", r.status_code == 200)

    # ── DB-layer RLS (connect as appuser; context drives visibility) ──────────
    # users RLS: auditor can read only their own profile row.
    async with AsyncSessionLocal() as s:
        u = IDS["auditor"]
        await set_user_context(s, role="auditor", user_id=str(u),
                               company_id=str((await _company_of(s, u))),
                               auth_user_id=AUTH["auditor"])
        rows = (await s.execute(select(User.email))).scalars().all()
        ck("auditor sees exactly 1 user row (self)", len(rows) == 1)

    # users RLS: owner sees all users in their company but NOT company B's owner.
    async with AsyncSessionLocal() as s:
        comp_a = await _company_of(s, IDS["owner"])
        await set_user_context(s, role="owner", user_id=str(IDS["owner"]),
                               company_id=str(comp_a), auth_user_id=AUTH["owner"])
        emails = set((await s.execute(select(User.email))).scalars().all())
        ck("owner sees company-A users (>=5)", len(emails) >= 5)
        comp_b_owner_email = await _email_of(IDS["owner_b"])
        ck("owner does NOT see company-B owner", comp_b_owner_email not in emails)

    # audit_tasks RLS: auditor sees only their task.
    async with AsyncSessionLocal() as s:
        await set_user_context(s, role="auditor", user_id=str(IDS["auditor"]),
                               company_id=str(await _company_of(s, IDS["auditor"])),
                               branch_id=str(await _branch_of(s, IDS["auditor"])),
                               auth_user_id=AUTH["auditor"])
        n = (await s.execute(select(func.count()).select_from(AuditTask))).scalar_one()
        ck("auditor sees exactly 1 task (own)", n == 1)

    # audit_tasks RLS: manager (branch1) sees only branch1 tasks (not branch2).
    async with AsyncSessionLocal() as s:
        await set_user_context(s, role="manager", user_id=str(IDS["manager"]),
                               company_id=str(await _company_of(s, IDS["manager"])),
                               branch_id=str(await _branch_of(s, IDS["manager"])),
                               auth_user_id=AUTH["manager"])
        n = (await s.execute(select(func.count()).select_from(AuditTask))).scalar_one()
        ck("manager (branch1) sees 1 task (branch scoped)", n == 1)

    # audit_tasks RLS: owner sees ALL company-A tasks (both branches).
    async with AsyncSessionLocal() as s:
        await set_user_context(s, role="owner", user_id=str(IDS["owner"]),
                               company_id=str(await _company_of(s, IDS["owner"])),
                               auth_user_id=AUTH["owner"])
        n = (await s.execute(select(func.count()).select_from(AuditTask))).scalar_one()
        ck("owner sees all company-A tasks (2)", n == 2)

    # A manager cannot change a user's role. Two layers protect this:
    #  - the users_update USING clause filters non-self/other-company rows out
    #    (so the UPDATE silently affects 0 rows), AND
    #  - even for a row a manager *could* touch, the role-change trigger raises.
    # Assert the effective outcome: the auditor's role is UNCHANGED.
    async with AsyncSessionLocal() as s:
        await set_user_context(s, role="manager", user_id=str(IDS["manager"]),
                               company_id=str(await _company_of(s, IDS["manager"])),
                               branch_id=str(await _branch_of(s, IDS["manager"])),
                               auth_user_id=AUTH["manager"])
        try:
            await s.execute(text("UPDATE public.users SET role='owner' WHERE id=:i"),
                            {"i": str(IDS["auditor"])})
            await s.commit()
        except Exception:
            await s.rollback()  # trigger may raise; either way role must be unchanged
    role_after = await _role_of(IDS["auditor"])
    ck("manager CANNOT change a user's role", role_after == "auditor")

    # The role-change trigger fires even for a row the actor can update: a
    # manager updating THEIR OWN row must still be blocked from a role change.
    async with AsyncSessionLocal() as s:
        await set_user_context(s, role="manager", user_id=str(IDS["manager"]),
                               company_id=str(await _company_of(s, IDS["manager"])),
                               branch_id=str(await _branch_of(s, IDS["manager"])),
                               auth_user_id=AUTH["manager"])
        raised = False
        try:
            await s.execute(text("UPDATE public.users SET role='owner' WHERE id=:i"),
                            {"i": str(IDS["manager"])})
            await s.commit()
        except Exception:
            raised = True
            await s.rollback()
        ck("role-change trigger blocks self-escalation", raised
           and (await _role_of(IDS["manager"])) == "manager")

    async with AsyncSessionLocal() as s:
        await set_user_context(s, role="owner", user_id=str(IDS["owner"]),
                               company_id=str(await _company_of(s, IDS["owner"])),
                               auth_user_id=AUTH["owner"])
        ok = False
        try:
            await s.execute(text("UPDATE public.users SET role='manager' WHERE id=:i"),
                            {"i": str(IDS["auditor"])})
            await s.commit()
            ok = True
        except Exception:
            await s.rollback()
        ck("owner CAN change a user's role", ok)
        # restore
        if ok:
            await s.execute(text("UPDATE public.users SET role='auditor' WHERE id=:i"),
                            {"i": str(IDS["auditor"])})
            await s.commit()

    # ── documents RLS: company isolation ─────────────────────────────────────
    async with AsyncSessionLocal() as s:
        await set_user_context(s, role="auditor", user_id=str(IDS["auditor"]),
                               company_id=str(await _company_of(s, IDS["auditor"])),
                               branch_id=str(await _branch_of(s, IDS["auditor"])),
                               auth_user_id=AUTH["auditor"])
        names = set((await s.execute(select(Document.original_filename))).scalars().all())
        ck("auditor sees company-A doc", "a.pdf" in names)
        ck("auditor does NOT see company-B doc", "b.pdf" not in names)

    async with AsyncSessionLocal() as s:
        await set_user_context(s, role="owner", user_id=str(IDS["owner_b"]),
                               company_id=str(await _company_of(s, IDS["owner_b"])),
                               auth_user_id=AUTH_OWNER_B)
        names = set((await s.execute(select(Document.original_filename))).scalars().all())
        ck("company-B owner sees only company-B doc", names == {"b.pdf"})

    # ── document_certifications RLS: scoped via parent doc's company ──────────
    async with AsyncSessionLocal() as s:
        await set_user_context(s, role="owner", user_id=str(IDS["owner_b"]),
                               company_id=str(await _company_of(s, IDS["owner_b"])),
                               auth_user_id=AUTH_OWNER_B)
        n = (await s.execute(select(func.count()).select_from(DocumentCertification))).scalar_one()
        ck("company-B owner sees 0 company-A certifications", n == 0)

    async with AsyncSessionLocal() as s:
        await set_user_context(s, role="owner", user_id=str(IDS["owner"]),
                               company_id=str(await _company_of(s, IDS["owner"])),
                               auth_user_id=AUTH["owner"])
        n = (await s.execute(select(func.count()).select_from(DocumentCertification))).scalar_one()
        ck("company-A owner sees 1 certification", n == 1)

    # auditor cannot insert a certification attributed to ANOTHER auditor.
    async with AsyncSessionLocal() as s:
        await set_user_context(s, role="auditor", user_id=str(IDS["auditor"]),
                               company_id=str(await _company_of(s, IDS["auditor"])),
                               branch_id=str(await _branch_of(s, IDS["auditor"])),
                               auth_user_id=AUTH["auditor"])
        blocked = False
        try:
            await s.execute(text(
                "INSERT INTO public.document_certifications (id, document_id, auditor_id, is_valid)"
                " VALUES (gen_random_uuid(), :d, :a, true)"),
                {"d": str(IDS["doc_a"]), "a": str(IDS["auditor2"])})
            await s.commit()
        except Exception:
            blocked = True
            await s.rollback()
        ck("auditor CANNOT certify as another auditor", blocked)

    # ── audit_ledger RLS: append-only (global SELECT/INSERT, no UPDATE/DELETE) ─
    async with AsyncSessionLocal() as s:
        await set_user_context(s, role="auditor", user_id=str(IDS["auditor"]),
                               company_id=str(await _company_of(s, IDS["auditor"])),
                               branch_id=str(await _branch_of(s, IDS["auditor"])),
                               auth_user_id=AUTH["auditor"])
        # auditor can INSERT a ledger entry (needed for task/cert auto-logging).
        from app.services.ledger_service import append_ledger_entry
        await append_ledger_entry(s, table_name="audit_tasks", record_id=IDS["auditor"],
                                  action=LedgerAction.update, created_by=IDS["auditor"],
                                  reason="rls-test")
        await s.commit()
        cnt = (await s.execute(select(func.count()).select_from(AuditLedger))).scalar_one()
        ck("auditor can append + SELECT ledger (global chain)", cnt >= 1)

    # ledger is immutable: UPDATE and DELETE are denied for everyone (even owner).
    async with AsyncSessionLocal() as s:
        await set_user_context(s, role="owner", user_id=str(IDS["owner"]),
                               company_id=str(await _company_of(s, IDS["owner"])),
                               auth_user_id=AUTH["owner"])
        upd_blocked = False
        try:
            res = await s.execute(text("UPDATE public.audit_ledger SET reason='tamper'"))
            await s.commit()
            # If RLS denies via 0 permissive policies, the UPDATE affects 0 rows.
            upd_blocked = (res.rowcount == 0)
        except Exception:
            upd_blocked = True
            await s.rollback()
        ck("ledger UPDATE blocked (immutable)", upd_blocked)

    async with AsyncSessionLocal() as s:
        await set_user_context(s, role="owner", user_id=str(IDS["owner"]),
                               company_id=str(await _company_of(s, IDS["owner"])),
                               auth_user_id=AUTH["owner"])
        del_blocked = False
        try:
            res = await s.execute(text("DELETE FROM public.audit_ledger"))
            await s.commit()
            del_blocked = (res.rowcount == 0)
        except Exception:
            del_blocked = True
            await s.rollback()
        # confirm rows still present
        await set_user_role(s, "admin")
        remaining = (await s.execute(select(func.count()).select_from(AuditLedger))).scalar_one()
        ck("ledger DELETE blocked (immutable)", del_blocked and remaining >= 1)

    await engine.dispose()
    print(f"\n=== {len(P)} passed, {len(F)} failed ===")
    return 1 if F else 0


async def _company_of(s, uid):
    # Read as platform role to fetch fixture metadata without RLS interference.
    async with AsyncSessionLocal() as s2:
        await set_user_role(s2, "admin")
        return (await s2.execute(select(User.company_id).where(User.id == uid))).scalar_one()


async def _branch_of(s, uid):
    async with AsyncSessionLocal() as s2:
        await set_user_role(s2, "admin")
        return (await s2.execute(select(User.branch_id).where(User.id == uid))).scalar_one()


async def _email_of(uid):
    async with AsyncSessionLocal() as s2:
        await set_user_role(s2, "admin")
        return (await s2.execute(select(User.email).where(User.id == uid))).scalar_one()


async def _role_of(uid):
    async with AsyncSessionLocal() as s2:
        await set_user_role(s2, "admin")
        r = (await s2.execute(select(User.role).where(User.id == uid))).scalar_one()
        return r.value if hasattr(r, "value") else str(r)


import sys
sys.exit(asyncio.run(main()))
