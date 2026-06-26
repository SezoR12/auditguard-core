-- Phase 4: task engine — is_critical flag + auditor_performance table
-- Idempotent; safe to re-run.

ALTER TABLE public.audit_tasks
  ADD COLUMN IF NOT EXISTS is_critical boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS public.auditor_performance (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  auditor_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  company_id uuid NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
  perf_date date NOT NULL,
  total_tasks int NOT NULL DEFAULT 0,
  tasks_completed int NOT NULL DEFAULT 0,
  tasks_completed_on_time int NOT NULL DEFAULT 0,
  tasks_delayed int NOT NULL DEFAULT 0,
  demerit_points int NOT NULL DEFAULT 0,
  efficiency_score numeric(6,2) NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_auditor_perf_day UNIQUE (auditor_id, perf_date)
);

CREATE INDEX IF NOT EXISTS ix_auditor_perf_company_date
  ON public.auditor_performance (company_id, perf_date);
