-- Mirror of backend/alembic/versions/001_initial_schema.py for pure-SQL deploys.
-- Alembic is the source of truth; this file is for environments that want to
-- apply the schema with psql instead of Alembic. Idempotent.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

DO $$ BEGIN CREATE TYPE company_tier AS ENUM ('essential','advanced','elite'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE user_role AS ENUM ('owner','gm','manager','auditor','admin','appowner'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE task_type AS ENUM ('document_review','field_visit','reconciliation','investigation','other'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE task_status AS ENUM ('pending','in_progress','completed','overdue'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE file_type AS ENUM ('excel','csv','word','image','pdf','encrypted_json'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE doc_category AS ENUM ('invoice','receipt','contract','report','statement','other'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE doc_status AS ENUM ('pending','ocr_processing','certified'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE ledger_action AS ENUM ('insert','update','delete','reverse'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE output_type AS ENUM ('dashboard','report','trust_index','summary'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE waste_category AS ENUM ('financial','operational','human','opportunity'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE severity AS ENUM ('low','medium','high','critical'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS public.companies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name varchar(255) NOT NULL,
  sector varchar(100) NOT NULL,
  tier company_tier NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.branches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
  name varchar(255) NOT NULL,
  location varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email varchar(255) UNIQUE NOT NULL,
  hashed_password varchar(255) NOT NULL,
  full_name varchar(255) NOT NULL,
  role user_role NOT NULL,
  branch_id uuid REFERENCES public.branches(id),
  company_id uuid NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.audit_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  auditor_id uuid NOT NULL REFERENCES public.users(id),
  title varchar(255) NOT NULL,
  task_type task_type NOT NULL,
  status task_status NOT NULL DEFAULT 'pending',
  sla_deadline timestamptz,
  completed_at timestamptz,
  demerit_points int NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  file_path varchar(1024) NOT NULL,
  original_filename varchar(512) NOT NULL,
  file_type file_type NOT NULL,
  doc_category doc_category NOT NULL,
  status doc_status NOT NULL DEFAULT 'pending',
  uploaded_by uuid NOT NULL REFERENCES public.users(id),
  company_id uuid NOT NULL REFERENCES public.companies(id),
  branch_id uuid REFERENCES public.branches(id),
  ocr_status varchar(50),
  confidence_score numeric(5,2),
  extracted_data jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.document_certifications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
  auditor_id uuid NOT NULL REFERENCES public.users(id),
  certified_at timestamptz NOT NULL DEFAULT now(),
  corrections_made jsonb,
  is_valid boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS public.audit_ledger (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  table_name varchar(128) NOT NULL,
  record_id uuid NOT NULL,
  action ledger_action NOT NULL,
  old_value jsonb,
  new_value jsonb,
  reason text,
  created_by uuid NOT NULL REFERENCES public.users(id),
  previous_hash text,
  current_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.analytics_outputs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES public.companies(id),
  output_type output_type NOT NULL,
  data jsonb NOT NULL,
  generated_at timestamptz NOT NULL DEFAULT now(),
  trust_index int
);

CREATE TABLE IF NOT EXISTS public.waste_map_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES public.companies(id),
  category waste_category NOT NULL,
  amount_iqd numeric(18,2) NOT NULL,
  department varchar(255) NOT NULL,
  description text NOT NULL,
  status varchar(50) NOT NULL DEFAULT 'open',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.risk_alerts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES public.companies(id),
  severity severity NOT NULL,
  title varchar(255) NOT NULL,
  description text NOT NULL,
  financial_impact numeric(18,2),
  status varchar(50) NOT NULL DEFAULT 'open',
  created_at timestamptz NOT NULL DEFAULT now()
);
