"""RLS policies for public.users and public.audit_tasks + session-context accessors

Revision ID: 008_rls_users_tasks
Revises: 007_templates
Create Date: 2026-06-26

Mirror of db/migrations/20260626000004_rls_users_tasks.sql. Applies on a
NON-superuser role (appuser) to actually enforce — Supabase's `postgres` role
has BYPASSRLS.
"""
from alembic import op

revision = "008_rls_users_tasks"
down_revision = "007_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure Supabase-auth mapping column exists (004 is Alembic-only; idempotent).
    op.execute("ALTER TABLE public.users ADD COLUMN IF NOT EXISTS auth_user_id uuid UNIQUE;")
    op.execute("ALTER TABLE public.users ALTER COLUMN hashed_password DROP NOT NULL;")

    # Typed session-context accessors (NULL-safe).
    op.execute("""
        CREATE OR REPLACE FUNCTION public.current_app_role() RETURNS text
          LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.current_user_role', true), '') $$;
        CREATE OR REPLACE FUNCTION public.current_app_user_id() RETURNS uuid
          LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid $$;
        CREATE OR REPLACE FUNCTION public.current_app_company_id() RETURNS uuid
          LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.current_company_id', true), '')::uuid $$;
        CREATE OR REPLACE FUNCTION public.current_app_branch_id() RETURNS uuid
          LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.current_branch_id', true), '')::uuid $$;
        CREATE OR REPLACE FUNCTION public.current_app_auth_user_id() RETURNS uuid
          LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.current_auth_user_id', true), '')::uuid $$;
        CREATE OR REPLACE FUNCTION public.current_app_auth_email() RETURNS text
          LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.current_auth_email', true), '') $$;
        CREATE OR REPLACE FUNCTION public.is_platform_role() RETURNS boolean
          LANGUAGE sql STABLE AS $$ SELECT public.current_app_role() IN ('admin', 'appowner') $$;
        CREATE OR REPLACE FUNCTION public.is_role_admin() RETURNS boolean
          LANGUAGE sql STABLE AS $$ SELECT public.current_app_role() IN ('owner', 'gm', 'admin', 'appowner') $$;
    """)

    # ── public.users ────────────────────────────────────────────────────────
    op.execute("ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE public.users FORCE  ROW LEVEL SECURITY;")

    op.execute("""
        DROP POLICY IF EXISTS users_select ON public.users;
        CREATE POLICY users_select ON public.users
          FOR SELECT USING (
            public.is_platform_role()
            OR auth_user_id = public.current_app_auth_user_id()
            OR email = public.current_app_auth_email()
            OR id = public.current_app_user_id()
            OR (public.current_app_role() IN ('owner', 'gm', 'manager')
                AND company_id = public.current_app_company_id())
          );

        DROP POLICY IF EXISTS users_insert ON public.users;
        CREATE POLICY users_insert ON public.users
          FOR INSERT WITH CHECK (
            public.is_platform_role()
            OR (public.current_app_role() IN ('owner', 'gm')
                AND company_id = public.current_app_company_id())
          );

        DROP POLICY IF EXISTS users_update ON public.users;
        CREATE POLICY users_update ON public.users
          FOR UPDATE
          USING (
            public.is_platform_role()
            OR (public.current_app_role() IN ('owner', 'gm') AND company_id = public.current_app_company_id())
            OR auth_user_id = public.current_app_auth_user_id()
            OR email = public.current_app_auth_email()
            OR id = public.current_app_user_id()
          )
          WITH CHECK (
            public.is_platform_role()
            OR (public.current_app_role() IN ('owner', 'gm') AND company_id = public.current_app_company_id())
            OR auth_user_id = public.current_app_auth_user_id()
            OR email = public.current_app_auth_email()
            OR id = public.current_app_user_id()
          );

        DROP POLICY IF EXISTS users_delete ON public.users;
        CREATE POLICY users_delete ON public.users
          FOR DELETE USING (
            public.is_platform_role()
            OR (public.current_app_role() IN ('owner', 'gm') AND company_id = public.current_app_company_id())
          );
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION public.enforce_role_change_privilege() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.role IS DISTINCT FROM OLD.role AND NOT public.is_role_admin() THEN
            RAISE EXCEPTION 'insufficient privilege to modify user role'
              USING ERRCODE = '42501';
          END IF;
          RETURN NEW;
        END;
        $$;
        DROP TRIGGER IF EXISTS trg_users_role_change ON public.users;
        CREATE TRIGGER trg_users_role_change
          BEFORE UPDATE ON public.users
          FOR EACH ROW EXECUTE FUNCTION public.enforce_role_change_privilege();
    """)

    # ── public.audit_tasks ───────────────────────────────────────────────────
    op.execute("ALTER TABLE public.audit_tasks ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE public.audit_tasks FORCE  ROW LEVEL SECURITY;")

    op.execute("""
        DROP POLICY IF EXISTS audit_tasks_access ON public.audit_tasks;
        CREATE POLICY audit_tasks_access ON public.audit_tasks
          FOR ALL
          USING (
            public.is_platform_role()
            OR (public.current_app_role() = 'auditor' AND auditor_id = public.current_app_user_id())
            OR (public.current_app_role() IN ('owner', 'gm') AND EXISTS (
                  SELECT 1 FROM public.users u
                  WHERE u.id = public.audit_tasks.auditor_id
                    AND u.company_id = public.current_app_company_id()))
            OR (public.current_app_role() = 'manager' AND EXISTS (
                  SELECT 1 FROM public.users u
                  WHERE u.id = public.audit_tasks.auditor_id
                    AND u.company_id = public.current_app_company_id()
                    AND u.branch_id IS NOT DISTINCT FROM public.current_app_branch_id()))
          )
          WITH CHECK (
            public.is_platform_role()
            OR (public.current_app_role() = 'auditor' AND auditor_id = public.current_app_user_id())
            OR (public.current_app_role() IN ('owner', 'gm') AND EXISTS (
                  SELECT 1 FROM public.users u
                  WHERE u.id = public.audit_tasks.auditor_id
                    AND u.company_id = public.current_app_company_id()))
            OR (public.current_app_role() = 'manager' AND EXISTS (
                  SELECT 1 FROM public.users u
                  WHERE u.id = public.audit_tasks.auditor_id
                    AND u.company_id = public.current_app_company_id()
                    AND u.branch_id IS NOT DISTINCT FROM public.current_app_branch_id()))
          );
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_users_role_change ON public.users;")
    op.execute("DROP FUNCTION IF EXISTS public.enforce_role_change_privilege();")
    op.execute("DROP POLICY IF EXISTS audit_tasks_access ON public.audit_tasks;")
    op.execute("ALTER TABLE public.audit_tasks DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS users_select ON public.users;")
    op.execute("DROP POLICY IF EXISTS users_insert ON public.users;")
    op.execute("DROP POLICY IF EXISTS users_update ON public.users;")
    op.execute("DROP POLICY IF EXISTS users_delete ON public.users;")
    op.execute("ALTER TABLE public.users DISABLE ROW LEVEL SECURITY;")
    for fn in (
        "current_app_role()", "current_app_user_id()", "current_app_company_id()",
        "current_app_branch_id()", "current_app_auth_user_id()", "current_app_auth_email()",
        "is_platform_role()", "is_role_admin()",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS public.{fn};")
