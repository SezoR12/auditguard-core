"""notifications + daily_digests + users.whatsapp_phone + RLS

Revision ID: 006_notifications
Revises: 005_ai_engine
Create Date: 2026-06-26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "006_notifications"
down_revision = "005_ai_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE public.users ADD COLUMN IF NOT EXISTS whatsapp_phone varchar(32)")

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("severity", sa.String(20), nullable=False, server_default="low"),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("financial_impact", sa.Numeric(18, 2), nullable=True),
        sa.Column("link", postgresql.JSONB(), nullable=True),
        sa.Column("ref_type", sa.String(40), nullable=True),
        sa.Column("ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("whatsapp_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        if_not_exists=True,
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_notif_company_created ON public.notifications (company_id, created_at)")

    op.create_table(
        "daily_digests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("digest_date", sa.Date(), nullable=False),
        sa.Column("waste_total_iqd", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("tasks_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_overdue", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("alerts_open", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trust_index", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("whatsapp_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("owner_id", "digest_date", name="uq_digest_owner_day"),
        if_not_exists=True,
    )

    # RLS: hide from auditor role (alerts/digests are owner-only).
    for tbl, pol in [("notifications", "auditor_no_access_notifications"),
                     ("daily_digests", "auditor_no_access_digests")]:
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
    op.execute("DROP TABLE IF EXISTS public.daily_digests")
    op.execute("DROP TABLE IF EXISTS public.notifications")
    op.execute("ALTER TABLE public.users DROP COLUMN IF EXISTS whatsapp_phone")
