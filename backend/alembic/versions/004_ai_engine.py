"""AI engine: cross_reference_findings + output_type enum values + RLS

Revision ID: 004_ai_engine
Revises: 003_tasks_perf
Create Date: 2026-06-26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "004_ai_engine"
down_revision = "003_tasks_perf"
branch_labels = None
depends_on = None

NEW_OUTPUT_TYPES = ["prediction", "narrative", "daily_snapshot"]


def upgrade() -> None:
    # 1. Add new enum values. ALTER TYPE ... ADD VALUE cannot run inside a
    #    transaction block, so commit the current one first.
    bind = op.get_bind()
    bind.execute(sa.text("COMMIT"))
    for val in NEW_OUTPUT_TYPES:
        bind.execute(sa.text(f"ALTER TYPE output_type ADD VALUE IF NOT EXISTS '{val}'"))
    # Re-open a transaction for the remaining DDL.
    bind.execute(sa.text("BEGIN"))

    # 2. cross_reference_findings table.
    op.create_table(
        "cross_reference_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("variance_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("variance_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column("severity", sa.String(50), nullable=False, server_default="medium"),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        if_not_exists=True,
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_xref_company "
        "ON public.cross_reference_findings (company_id, created_at)"
    )

    # 3. RLS hide from auditor.
    op.execute("ALTER TABLE public.cross_reference_findings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.cross_reference_findings FORCE  ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS auditor_no_access_xref ON public.cross_reference_findings")
    op.execute(
        """
        CREATE POLICY auditor_no_access_xref ON public.cross_reference_findings
          FOR ALL
          USING      (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor')
          WITH CHECK (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor')
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.cross_reference_findings")
    # Note: enum values are not removed (Postgres can't easily drop enum values).
