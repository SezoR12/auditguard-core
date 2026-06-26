-- Phase 11: template engine + CRaaS + consolidated federation schema. Idempotent.

CREATE TABLE IF NOT EXISTS public.report_templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name varchar(255) NOT NULL,
  description text,
  sectors jsonb,
  config jsonb NOT NULL,
  version int NOT NULL DEFAULT 1,
  is_published boolean NOT NULL DEFAULT false,
  created_by uuid REFERENCES public.users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.report_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
  requested_by uuid REFERENCES public.users(id) ON DELETE SET NULL,
  title varchar(255) NOT NULL,
  requirements text,
  status varchar(40) NOT NULL DEFAULT 'requested',
  price_iqd numeric(18,2),
  template_id uuid REFERENCES public.report_templates(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_report_requests_company ON public.report_requests (company_id, status);

CREATE TABLE IF NOT EXISTS public.custom_reports (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
  template_id uuid NOT NULL REFERENCES public.report_templates(id) ON DELETE CASCADE,
  name varchar(255) NOT NULL,
  config_snapshot jsonb NOT NULL,
  is_active boolean NOT NULL DEFAULT true,
  deployed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_custom_reports_company ON public.custom_reports (company_id);

CREATE TABLE IF NOT EXISTS public.consolidated_entities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_company_id uuid NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
  entity_name varchar(255) NOT NULL,
  box_identifier varchar(255) NOT NULL,
  region varchar(120),
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.consolidated_metrics (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_company_id uuid NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
  entity_id uuid NOT NULL REFERENCES public.consolidated_entities(id) ON DELETE CASCADE,
  metric_key varchar(80) NOT NULL,
  metric_value numeric(20,2),
  period varchar(20) NOT NULL,
  payload jsonb,
  federated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.report_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.report_requests FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS auditor_no_access_report_requests ON public.report_requests;
CREATE POLICY auditor_no_access_report_requests ON public.report_requests
  FOR ALL
  USING      (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor')
  WITH CHECK (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor');

ALTER TABLE public.custom_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.custom_reports FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS auditor_no_access_custom_reports ON public.custom_reports;
CREATE POLICY auditor_no_access_custom_reports ON public.custom_reports
  FOR ALL
  USING      (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor')
  WITH CHECK (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor');
