// Fetch a protected endpoint (with the Supabase bearer token) and trigger a
// browser download of the returned blob (used for PDF generation/preview).
import { supabaseAuditcore } from "@/lib/supabaseClient";

export async function downloadAuthed(url: string, filename: string): Promise<void> {
  const { data } = await supabaseAuditcore.auth.getSession();
  const token = data.session?.access_token;
  const res = await fetch(url, {
    method: url.includes("/preview") || url.includes("/generate") ? "POST" : "GET",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      detail = (await res.json())?.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}
