// AuditCore — direct client to the EXTERNAL Supabase project (#1).
// This is separate from `@/integrations/supabase/client` which is the
// Lovable Cloud auto-generated client and points at a different project.
//
// Set in .env (Lovable preview will need these):
//   VITE_AUDITCORE_SUPABASE_URL=https://<project-ref>.supabase.co
//   VITE_AUDITCORE_SUPABASE_ANON_KEY=...

import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_AUDITCORE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_AUDITCORE_SUPABASE_ANON_KEY as string | undefined;

if (!url || !anonKey) {
  // Don't crash module-load; surface a runtime error if something tries to use it.
  console.warn(
    "[auditcore] VITE_AUDITCORE_SUPABASE_URL or VITE_AUDITCORE_SUPABASE_ANON_KEY missing — supabaseClient is disabled.",
  );
}

export const supabaseAuditcore = createClient(url ?? "http://localhost", anonKey ?? "missing", {
  auth: { persistSession: false, autoRefreshToken: false },
});
