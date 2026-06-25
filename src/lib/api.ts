// Thin fetch wrapper for the FastAPI backend.
const API_URL =
  (import.meta.env.VITE_AUDITCORE_API_URL as string | undefined) ?? "http://localhost:8000";

const TOKEN_KEY = "auditcore.access_token";
const REFRESH_KEY = "auditcore.refresh_token";

export const tokens = {
  get access() {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(TOKEN_KEY);
  },
  get refresh() {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(REFRESH_KEY);
  },
  set(access: string, refresh: string) {
    window.localStorage.setItem(TOKEN_KEY, access);
    window.localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_KEY);
  },
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (tokens.access) headers.set("Authorization", `Bearer ${tokens.access}`);

  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string;
  role: "owner" | "gm" | "manager" | "auditor" | "admin" | "appowner";
  company_id: string;
  branch_id: string | null;
  is_active: boolean;
}

export const api = {
  login: (email: string, password: string) =>
    request<TokenPair>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => request<CurrentUser>("/auth/me"),
  refresh: (refresh_token: string) =>
    request<TokenPair>("/auth/refresh", { method: "POST", body: JSON.stringify({ refresh_token }) }),
};
