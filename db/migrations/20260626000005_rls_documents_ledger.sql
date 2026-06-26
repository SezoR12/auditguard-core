-- Row-Level Security for public.documents, public.document_certifications and
-- public.audit_ledger — extends the company/branch isolation model from
-- 20260626000004_rls_users_tasks.sql to the remaining tenant-data tables.
--
-- Relies on the same session-context accessors defined there:
--   public.current_app_role() / current_app_company_id() /
--   current_app_branch_id() / current_app_user_id() / is_platform_role()
-- which the app sets per request in app/api/deps.py::get_current_user via
-- app/database.py::set_user_context. Enforced only under a NON-superuser role
-- (appuser); Supabase's `postgres` role has BYPASSRLS.

-- ── public.documents ────────────────────────────────────────────────────────
-- Tenant isolation by company. All client roles (owner/gm/manager/auditor) work
-- WITHIN their own company; the API further narrows by uploader/branch/status.
-- Auditors legitimately read company-wide pending docs (certification queue) and
-- insert/update their own uploads, so the row scope is company-level here.
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.documents FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS documents_access ON public.documents;
CREATE POLICY documents_access ON public.documents
  FOR ALL
  USING (
    public.is_platform_role()
    OR company_id = public.current_app_company_id()
  )
  WITH CHECK (
    public.is_platform_role()
    OR company_id = public.current_app_company_id()
  );

-- ── public.document_certifications ──────────────────────────────────────────
-- No company column of its own: scope is derived from the parent document's
-- company. Auditors may insert only certifications attributed to themselves.
ALTER TABLE public.document_certifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_certifications FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS certifications_select ON public.document_certifications;
CREATE POLICY certifications_select ON public.document_certifications
  FOR SELECT USING (
    public.is_platform_role()
    OR EXISTS (
      SELECT 1 FROM public.documents d
      WHERE d.id = public.document_certifications.document_id
        AND d.company_id = public.current_app_company_id())
  );

DROP POLICY IF EXISTS certifications_insert ON public.document_certifications;
CREATE POLICY certifications_insert ON public.document_certifications
  FOR INSERT WITH CHECK (
    public.is_platform_role()
    OR (
      EXISTS (
        SELECT 1 FROM public.documents d
        WHERE d.id = public.document_certifications.document_id
          AND d.company_id = public.current_app_company_id())
      -- Auditors can only attribute a certification to themselves; management
      -- roles (manager/gm/owner) may certify on behalf within their company.
      AND (
        public.current_app_role() <> 'auditor'
        OR auditor_id = public.current_app_user_id()
      )
    )
  );

-- A certification is an immutable attestation: no UPDATE/DELETE for anyone
-- (no permissive policy for those commands + FORCE RLS => denied, incl. owner).

-- ── public.audit_ledger ─────────────────────────────────────────────────────
-- The ledger is a SINGLE global, hash-chained, append-only log. Its integrity
-- depends on global visibility: append_ledger_entry()::get_last_hash reads the
-- latest row to chain onto, and ANY authenticated actor (including auditors, who
-- append on task completion / certification) must be able to SELECT it and
-- INSERT. Therefore we do NOT row-scope SELECT/INSERT — instead we enforce true
-- immutability: UPDATE and DELETE are denied for EVERYONE (no permissive policy
-- for those commands under FORCE RLS), matching the app invariant that no
-- update/delete path exists. Read access in the UI stays owner-gated at the API.
ALTER TABLE public.audit_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_ledger FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ledger_select ON public.audit_ledger;
CREATE POLICY ledger_select ON public.audit_ledger
  FOR SELECT USING (true);

DROP POLICY IF EXISTS ledger_insert ON public.audit_ledger;
CREATE POLICY ledger_insert ON public.audit_ledger
  FOR INSERT WITH CHECK (true);

-- Intentionally NO ledger_update / ledger_delete policies → append-only.
