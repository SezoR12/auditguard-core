// AuditCore — direct client to the EXTERNAL Supabase project (#1).
// Separate from `@/integrations/supabase/client` (the Lovable Cloud client,
// different project). This one persists the session because the SPA logs in
// directly via Supabase Auth and forwards the access token to FastAPI.
//
// Required env:
//   VITE_AUDITCORE_SUPABASE_URL=https://<project-ref>.supabase.co
//   VITE_AUDITCORE_SUPABASE_ANON_KEY=...

import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_AUDITCORE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_AUDITCORE_SUPABASE_ANON_KEY as string | undefined;

if (!url || !anonKey) {
  console.warn(
    "[auditcore] VITE_AUDITCORE_SUPABASE_URL or VITE_AUDITCORE_SUPABASE_ANON_KEY missing — auth is disabled.",
  );
}

export const supabaseAuditcore = createClient(url ?? "http://localhost", anonKey ?? "missing", {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    storageKey: "auditcore.supabase.session",
    detectSessionInUrl: false,
  },
});
