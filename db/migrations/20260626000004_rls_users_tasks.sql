-- Row-Level Security for public.users and public.audit_tasks.
--
-- Builds on the session-GUC model already used by 20260625000001_rls_auditor_hide.sql
-- (app.current_user_role). The application sets a richer context per request in
-- app/api/deps.py::get_current_user via app/database.py::set_user_context:
--
--   app.current_user_role      -- resolved public.users.role
--   app.current_user_id        -- resolved public.users.id
--   app.current_company_id     -- resolved public.users.company_id
--   app.current_branch_id      -- resolved public.users.branch_id (may be empty)
--   app.current_auth_user_id   -- Supabase JWT "sub" (auth.users id) — set BEFORE the
--                                 profile lookup so the bootstrap self-read passes RLS
--   app.current_auth_email     -- JWT "email" claim — supports email-fallback linking
--
-- These MUST be applied on a NON-superuser connection (appuser). Supabase's
-- `postgres` role has BYPASSRLS, so RLS only actually enforces for appuser.

-- Self-contained: ensure the Supabase-auth mapping column exists (the 004
-- migration is Alembic-only). Idempotent so apply order does not matter.
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS auth_user_id uuid UNIQUE;
ALTER TABLE public.users ALTER COLUMN hashed_password DROP NOT NULL;

-- ── Typed accessors for the session context (NULL-safe) ─────────────────────
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

-- App-level roles see everything (admin/appowner = platform + system workers).
CREATE OR REPLACE FUNCTION public.is_platform_role() RETURNS boolean
  LANGUAGE sql STABLE AS $$ SELECT public.current_app_role() IN ('admin', 'appowner') $$;

-- Roles permitted to modify a user's role column.
CREATE OR REPLACE FUNCTION public.is_role_admin() RETURNS boolean
  LANGUAGE sql STABLE AS $$ SELECT public.current_app_role() IN ('owner', 'gm', 'admin', 'appowner') $$;

-- ── public.users ────────────────────────────────────────────────────────────
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users FORCE  ROW LEVEL SECURITY;

-- SELECT: platform roles (full) · self (3 ways, incl. pre-resolution bootstrap)
--         · owner/gm/manager limited to their own company.
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

-- INSERT: platform roles, or owner/gm creating within their own company.
DROP POLICY IF EXISTS users_insert ON public.users;
CREATE POLICY users_insert ON public.users
  FOR INSERT WITH CHECK (
    public.is_platform_role()
    OR (public.current_app_role() IN ('owner', 'gm')
        AND company_id = public.current_app_company_id())
  );

-- UPDATE: platform roles, owner/gm within company, or the user editing their own
-- row (incl. the auth_user_id backfill during login). Role-column changes are
-- separately gated by the trigger below.
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

-- DELETE: platform roles, or owner/gm within company.
DROP POLICY IF EXISTS users_delete ON public.users;
CREATE POLICY users_delete ON public.users
  FOR DELETE USING (
    public.is_platform_role()
    OR (public.current_app_role() IN ('owner', 'gm') AND company_id = public.current_app_company_id())
  );

-- Only owners/admins may change a user's role (column-level rule via trigger,
-- which also binds even where USING already permits the row update).
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

-- ── public.audit_tasks ──────────────────────────────────────────────────────
-- audit_tasks has no company/branch column; scope is derived from the assigned
-- auditor's user row. Auditors see ONLY their own assigned tasks; managers are
-- limited to their company+branch; owner/gm to their company; platform = all.
ALTER TABLE public.audit_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_tasks FORCE  ROW LEVEL SECURITY;

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
