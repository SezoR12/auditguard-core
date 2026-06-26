"""template engine + CRaaS + consolidated federation schema

Revision ID: 007_templates
Revises: 006_notifications
Create Date: 2026-06-26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "007_templates"
down_revision = "006_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sectors", postgresql.JSONB(), nullable=True),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        if_not_exists=True,
    )

    op.create_table(
        "report_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("requirements", sa.Text(), nullable=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="requested"),
        sa.Column("price_iqd", sa.Numeric(18, 2), nullable=True),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("report_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        if_not_exists=True,
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_report_requests_company ON public.report_requests (company_id, status)")

    op.create_table(
        "custom_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deployed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        if_not_exists=True,
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_custom_reports_company ON public.custom_reports (company_id)")

    op.create_table(
        "consolidated_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("parent_company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_name", sa.String(255), nullable=False),
        sa.Column("box_identifier", sa.String(255), nullable=False),
        sa.Column("region", sa.String(120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        if_not_exists=True,
    )
    op.create_table(
        "consolidated_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("parent_company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consolidated_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric_key", sa.String(80), nullable=False),
        sa.Column("metric_value", sa.Numeric(20, 2), nullable=True),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("federated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        if_not_exists=True,
    )

    # RLS: client-facing CRaaS tables are hidden from the auditor role.
    for tbl, pol in [
        ("report_requests", "auditor_no_access_report_requests"),
        ("custom_reports", "auditor_no_access_custom_reports"),
    ]:
        op.execute(f"ALTER TABLE public.{tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{tbl} FORCE  ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {pol} ON public.{tbl}")
        op.execute(
            f"""
            CREATE POLICY {pol} ON public.{tbl}
              FOR ALL
              USING      (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor')
              WITH CHECK (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor')
            """
        )


def downgrade() -> None:
    for t in ["consolidated_metrics", "consolidated_entities", "custom_reports", "report_requests", "report_templates"]:
        op.execute(f"DROP TABLE IF EXISTS public.{t}")
