// Backend health probe — lets the UI decide between "full backend" and
// "Supabase-only" mode. Wraps GET /health (deep check: db + redis + rls) with a
// short timeout so a hung/missing backend never blocks the UI.

import { API_URL } from "@/lib/api";

export type BackendMode = "full" | "supabase-only";

export interface BackendHealth {
  /** Whether GET /health returned 2xx within the timeout. */
  reachable: boolean;
  /** "full" when reachable, else "supabase-only". */
  mode: BackendMode;
  /** Overall status from /health ("ok" | "degraded") when reachable. */
  status: string | null;
  /** Per-subsystem checks from /health (database/redis/rls) when present. */
  checks: Record<string, string> | null;
  /** HTTP status code (0 = network error / unreachable). */
  httpStatus: number;
  /** Populated on failure for console/debug. */
  error: string | null;
}

const DEFAULT_TIMEOUT_MS = 4000;

export async function checkBackendHealth(
  apiUrl: string = API_URL,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<BackendHealth> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${apiUrl}/health`, {
      method: "GET",
      signal: controller.signal,
    });
    let body: { status?: string; checks?: Record<string, string> } | null = null;
    try {
      body = await res.json();
    } catch {
      /* /health should be JSON, but tolerate non-JSON */
    }
    const reachable = res.ok;
    return {
      reachable,
      mode: reachable ? "full" : "supabase-only",
      status: body?.status ?? null,
      checks: body?.checks ?? null,
      httpStatus: res.status,
      error: reachable ? null : `HTTP ${res.status}`,
    };
  } catch (err) {
    const aborted = err instanceof DOMException && err.name === "AbortError";
    return {
      reachable: false,
      mode: "supabase-only",
      status: null,
      checks: null,
      httpStatus: 0,
      error: aborted ? `timeout after ${timeoutMs}ms` : String(err),
    };
  } finally {
    clearTimeout(timer);
  }
}
