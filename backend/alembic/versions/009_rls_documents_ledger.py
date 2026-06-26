"""RLS for documents, document_certifications and audit_ledger

Revision ID: 009_rls_documents_ledger
Revises: 008_rls_users_tasks
Create Date: 2026-06-26

Mirror of db/migrations/20260626000005_rls_documents_ledger.sql. Extends company
isolation to documents + certifications; enforces append-only immutability on the
global hash-chained audit_ledger. Applies on a NON-superuser role (appuser).
"""
from alembic import op

revision = "009_rls_documents_ledger"
down_revision = "008_rls_users_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # documents — company isolation.
    op.execute("ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE public.documents FORCE  ROW LEVEL SECURITY;")
    op.execute("""
        DROP POLICY IF EXISTS documents_access ON public.documents;
        CREATE POLICY documents_access ON public.documents
          FOR ALL
          USING (public.is_platform_role() OR company_id = public.current_app_company_id())
          WITH CHECK (public.is_platform_role() OR company_id = public.current_app_company_id());
    """)

    # document_certifications — scope via parent document; auditors self-attribute.
    op.execute("ALTER TABLE public.document_certifications ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE public.document_certifications FORCE  ROW LEVEL SECURITY;")
    op.execute("""
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
              AND (
                public.current_app_role() <> 'auditor'
                OR auditor_id = public.current_app_user_id()
              )
            )
          );
    """)

    # audit_ledger — append-only immutability; global SELECT/INSERT.
    op.execute("ALTER TABLE public.audit_ledger ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE public.audit_ledger FORCE  ROW LEVEL SECURITY;")
    op.execute("""
        DROP POLICY IF EXISTS ledger_select ON public.audit_ledger;
        CREATE POLICY ledger_select ON public.audit_ledger FOR SELECT USING (true);
        DROP POLICY IF EXISTS ledger_insert ON public.audit_ledger;
        CREATE POLICY ledger_insert ON public.audit_ledger FOR INSERT WITH CHECK (true);
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ledger_insert ON public.audit_ledger;")
    op.execute("DROP POLICY IF EXISTS ledger_select ON public.audit_ledger;")
    op.execute("ALTER TABLE public.audit_ledger DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS certifications_insert ON public.document_certifications;")
    op.execute("DROP POLICY IF EXISTS certifications_select ON public.document_certifications;")
    op.execute("ALTER TABLE public.document_certifications DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS documents_access ON public.documents;")
    op.execute("ALTER TABLE public.documents DISABLE ROW LEVEL SECURITY;")
