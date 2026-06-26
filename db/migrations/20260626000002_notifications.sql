-- Phase 8: notifications + daily_digests + users.whatsapp_phone + RLS. Idempotent.

ALTER TABLE public.users ADD COLUMN IF NOT EXISTS whatsapp_phone varchar(32);

CREATE TABLE IF NOT EXISTS public.notifications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
  user_id uuid REFERENCES public.users(id) ON DELETE CASCADE,
  severity varchar(20) NOT NULL DEFAULT 'low',
  category varchar(40) NOT NULL,
  title varchar(255) NOT NULL,
  body text NOT NULL,
  financial_impact numeric(18,2),
  link jsonb,
  ref_type varchar(40),
  ref_id uuid,
  is_read boolean NOT NULL DEFAULT false,
  whatsapp_sent boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_notif_company_created ON public.notifications (company_id, created_at);

CREATE TABLE IF NOT EXISTS public.daily_digests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
  owner_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  digest_date date NOT NULL,
  waste_total_iqd numeric(18,2) NOT NULL DEFAULT 0,
  tasks_completed int NOT NULL DEFAULT 0,
  tasks_overdue int NOT NULL DEFAULT 0,
  alerts_open int NOT NULL DEFAULT 0,
  trust_index int,
  message text NOT NULL,
  whatsapp_sent boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_digest_owner_day UNIQUE (owner_id, digest_date)
);

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS auditor_no_access_notifications ON public.notifications;
CREATE POLICY auditor_no_access_notifications ON public.notifications
  FOR ALL
  USING      (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor')
  WITH CHECK (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor');

ALTER TABLE public.daily_digests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_digests FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS auditor_no_access_digests ON public.daily_digests;
CREATE POLICY auditor_no_access_digests ON public.daily_digests
  FOR ALL
  USING      (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor')
  WITH CHECK (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor');
