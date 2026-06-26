-- Phase 6: AI engine — cross_reference_findings table + enum additions + RLS.
-- Idempotent; safe to re-run.

-- 1. New output_type enum values (prediction, narrative, daily_snapshot)
DO $$ BEGIN ALTER TYPE output_type ADD VALUE IF NOT EXISTS 'prediction'; EXCEPTION WHEN others THEN NULL; END $$;
DO $$ BEGIN ALTER TYPE output_type ADD VALUE IF NOT EXISTS 'narrative'; EXCEPTION WHEN others THEN NULL; END $$;
DO $$ BEGIN ALTER TYPE output_type ADD VALUE IF NOT EXISTS 'daily_snapshot'; EXCEPTION WHEN others THEN NULL; END $$;

-- 2. cross_reference_findings (auditor-restricted)
CREATE TABLE IF NOT EXISTS public.cross_reference_findings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
  finding_type varchar(64) NOT NULL,
  description text NOT NULL,
  variance_amount numeric(18,2),
  variance_pct numeric(8,2),
  severity varchar(50) NOT NULL DEFAULT 'medium',
  details jsonb,
  status varchar(50) NOT NULL DEFAULT 'open',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_xref_company ON public.cross_reference_findings (company_id, created_at);

-- 3. RLS: hide from the auditor role (same pattern as analytics/waste/risk)
ALTER TABLE public.cross_reference_findings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cross_reference_findings FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS auditor_no_access_xref ON public.cross_reference_findings;
CREATE POLICY auditor_no_access_xref ON public.cross_reference_findings
  FOR ALL
  USING      (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor')
  WITH CHECK (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor');
