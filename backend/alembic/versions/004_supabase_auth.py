"""link users to supabase auth.users

Revision ID: 004_supabase_auth
Revises: 003_tasks_perf
Create Date: 2026-06-26
"""
from alembic import op

revision = "004_supabase_auth"
down_revision = "003_tasks_perf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # auth_user_id links public.users to Supabase auth.users(id).
    # Nullable so existing rows remain valid until the seed/admin script backfills.
    op.execute(
        "ALTER TABLE public.users "
        "ADD COLUMN IF NOT EXISTS auth_user_id uuid UNIQUE"
    )
    # hashed_password is no longer used (Supabase Auth owns credentials),
    # but we keep the column for backward compat. Make it nullable.
    op.execute("ALTER TABLE public.users ALTER COLUMN hashed_password DROP NOT NULL")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_users_auth_user_id ON public.users(auth_user_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS public.ix_users_auth_user_id")
    op.execute("ALTER TABLE public.users DROP COLUMN IF EXISTS auth_user_id")
