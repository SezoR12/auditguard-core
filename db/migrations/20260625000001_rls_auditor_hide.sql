-- Row-level security: hide analytics/waste/risk tables from the auditor role.
-- The application MUST call: SELECT set_user_role('<role>') on every connection
-- before issuing queries. FastAPI wires this in app/api/deps.py::get_current_user.

CREATE OR REPLACE FUNCTION public.set_user_role(role text)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM set_config('app.current_user_role', role, false);
END;
$$;

ALTER TABLE public.analytics_outputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.analytics_outputs FORCE  ROW LEVEL SECURITY;
ALTER TABLE public.waste_map_items   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.waste_map_items   FORCE  ROW LEVEL SECURITY;
ALTER TABLE public.risk_alerts       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risk_alerts       FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS auditor_no_access_analytics ON public.analytics_outputs;
CREATE POLICY auditor_no_access_analytics ON public.analytics_outputs
  FOR ALL
  USING      (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor')
  WITH CHECK (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor');

DROP POLICY IF EXISTS auditor_no_access_waste ON public.waste_map_items;
CREATE POLICY auditor_no_access_waste ON public.waste_map_items
  FOR ALL
  USING      (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor')
  WITH CHECK (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor');

DROP POLICY IF EXISTS auditor_no_access_risk ON public.risk_alerts;
CREATE POLICY auditor_no_access_risk ON public.risk_alerts
  FOR ALL
  USING      (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor')
  WITH CHECK (current_setting('app.current_user_role', true) IS DISTINCT FROM 'auditor');
