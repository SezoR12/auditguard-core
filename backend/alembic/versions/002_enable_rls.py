"""enable RLS + auditor hide policies + verification

Revision ID: 002_rls
Revises: 001_initial
Create Date: 2026-06-25
"""
from alembic import op

revision = "002_rls"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Helper function — sets the per-connection role used by RLS policies
    op.execute("""
        CREATE OR REPLACE FUNCTION public.set_user_role(role text)
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        BEGIN
            PERFORM set_config('app.current_user_role', role, false);
        END;
        $$;
    """)

    for tbl in ("analytics_outputs", "waste_map_items", "risk_alerts"):
        op.execute(f"ALTER TABLE public.{tbl} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE public.{tbl} FORCE ROW LEVEL SECURITY;")

    op.execute("""
        CREATE POLICY auditor_no_access_analytics ON public.analytics_outputs
        FOR ALL
        USING (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor')
        WITH CHECK (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor');
    """)
    op.execute("""
        CREATE POLICY auditor_no_access_waste ON public.waste_map_items
        FOR ALL
        USING (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor')
        WITH CHECK (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor');
    """)
    op.execute("""
        CREATE POLICY auditor_no_access_risk ON public.risk_alerts
        FOR ALL
        USING (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor')
        WITH CHECK (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor');
    """)

    # ---- Verification: insert a probe row, switch role to auditor, expect 0 rows.
    bind = op.get_bind()

    # Need an existing company_id; create a throwaway company.
    company_id = bind.exec_driver_sql(
        "INSERT INTO companies (name, sector, tier) "
        "VALUES ('__rls_probe__', 'test', 'essential') RETURNING id"
    ).scalar()

    bind.exec_driver_sql(
        "INSERT INTO analytics_outputs (company_id, output_type, data, trust_index) "
        "VALUES (%s, 'dashboard', '{}'::jsonb, 50)",
        (company_id,),
    )

    bind.exec_driver_sql("SELECT set_user_role('auditor')")
    auditor_count = bind.exec_driver_sql("SELECT count(*) FROM analytics_outputs").scalar()

    bind.exec_driver_sql("SELECT set_user_role('owner')")
    owner_count = bind.exec_driver_sql("SELECT count(*) FROM analytics_outputs").scalar()

    # Reset
    bind.exec_driver_sql("SELECT set_user_role('')")
    bind.exec_driver_sql("DELETE FROM analytics_outputs WHERE company_id = %s", (company_id,))
    bind.exec_driver_sql("DELETE FROM companies WHERE id = %s", (company_id,))

    if auditor_count != 0:
        raise RuntimeError(f"RLS verification FAILED: auditor saw {auditor_count} analytics rows (expected 0)")
    if owner_count < 1:
        raise RuntimeError(f"RLS verification FAILED: owner saw {owner_count} rows (expected >= 1)")
    print(f"[RLS] OK — auditor={auditor_count} rows, owner={owner_count} rows")


def downgrade() -> None:
    for tbl, pol in (
        ("analytics_outputs", "auditor_no_access_analytics"),
        ("waste_map_items", "auditor_no_access_waste"),
        ("risk_alerts", "auditor_no_access_risk"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {pol} ON public.{tbl};")
        op.execute(f"ALTER TABLE public.{tbl} DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP FUNCTION IF EXISTS public.set_user_role(text);")
