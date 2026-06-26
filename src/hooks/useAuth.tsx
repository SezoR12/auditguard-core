import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { supabaseAuditcore } from "@/lib/supabaseClient";
import { api, type CurrentUser } from "@/lib/api";

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<CurrentUser>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  const loadProfile = useCallback(async () => {
    const { data } = await supabaseAuditcore.auth.getSession();
    if (!data.session) {
      setUser(null);
      return;
    }
    try {
      setUser(await api.me());
    } catch {
      // Token valid but no profile / inactive — sign out to clear state.
      await supabaseAuditcore.auth.signOut();
      setUser(null);
    }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      await loadProfile();
    } finally {
      setLoading(false);
    }
  }, [loadProfile]);

  useEffect(() => {
    void refresh();
    const { data: sub } = supabaseAuditcore.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_IN" || event === "SIGNED_OUT" || event === "USER_UPDATED") {
        void loadProfile();
      }
    });
    return () => sub.subscription.unsubscribe();
  }, [refresh, loadProfile]);

  const login = useCallback(async (email: string, password: string) => {
    // Prefer the rate-limited backend proxy; set the Supabase session from the
    // returned tokens. Fall back to direct Supabase login if the proxy is
    // unreachable (e.g. backend not deployed yet).
    try {
      const tokens = await api.login(email, password);
      await supabaseAuditcore.auth.setSession({
        access_token: tokens.access_token,
        refresh_token: tokens.refresh_token ?? "",
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      // 429/401 from the proxy carry an Arabic detail — surface it as-is.
      if (/محاولات|قفل|غير صحيحة/.test(msg)) throw new Error(msg);
      // Network/HTTP-5xx (proxy down) → fall back to direct Supabase login.
      const { error } = await supabaseAuditcore.auth.signInWithPassword({ email, password });
      if (error) {
        throw new Error(
          /invalid|credentials|password/i.test(error.message)
            ? "البريد الإلكتروني أو كلمة المرور غير صحيحة"
            : error.message,
        );
      }
    }
    const me = await api.me();
    setUser(me);
    return me;
  }, []);

  const logout = useCallback(async () => {
    // Hard-revoke the token server-side (best-effort), then clear the session.
    try {
      await api.logout();
    } catch {
      /* ignore — proceed to local sign-out regardless */
    }
    await supabaseAuditcore.auth.signOut();
    setUser(null);
  }, []);

  // 15-minute inactivity auto-logout (security hardening). Resets on user
  // activity; only active while logged in.
  useEffect(() => {
    if (!user) return;
    const IDLE_MS = 15 * 60 * 1000;
    let timer: ReturnType<typeof setTimeout>;
    const reset = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        void logout();
      }, IDLE_MS);
    };
    const events = ["mousedown", "keydown", "scroll", "touchstart", "visibilitychange"];
    events.forEach((e) => window.addEventListener(e, reset, { passive: true }));
    reset();
    return () => {
      clearTimeout(timer);
      events.forEach((e) => window.removeEventListener(e, reset));
    };
  }, [user, logout]);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

export function roleHomePath(role: CurrentUser["role"]): string {
  switch (role) {
    case "owner": return "/owner";
    case "auditor": return "/auditor";
    case "manager": return "/manager";
    case "gm": return "/gm";
    case "appowner": return "/appowner";
    case "admin": return "/appowner";
    default: return "/";
  }
}
