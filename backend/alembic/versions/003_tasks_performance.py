"""task engine: is_critical flag + auditor_performance table

Revision ID: 003_tasks_perf
Revises: 002_rls
Create Date: 2026-06-26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "003_tasks_perf"
down_revision = "002_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. is_critical flag on audit_tasks (idempotent for safety).
    op.execute(
        "ALTER TABLE public.audit_tasks "
        "ADD COLUMN IF NOT EXISTS is_critical boolean NOT NULL DEFAULT false"
    )

    # 2. auditor_performance aggregation table.
    op.create_table(
        "auditor_performance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("auditor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("perf_date", sa.Date(), nullable=False),
        sa.Column("total_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_completed_on_time", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_delayed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("demerit_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("efficiency_score", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("auditor_id", "perf_date", name="uq_auditor_perf_day"),
        if_not_exists=True,
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_auditor_perf_company_date "
        "ON public.auditor_performance (company_id, perf_date)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.auditor_performance")
    op.execute("ALTER TABLE public.audit_tasks DROP COLUMN IF EXISTS is_critical")
