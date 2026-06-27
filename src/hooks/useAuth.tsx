import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { supabaseAuditcore } from "@/lib/supabaseClient";
import { api, type CurrentUser } from "@/lib/api";
import { loadProfileFromSupabase, PREVIEW_BACKEND_HELP, PreviewBackendUnavailableError } from "@/lib/authPreview";

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  authHint: string | null;
  login: (email: string, password: string) => Promise<CurrentUser>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  clearAuthHint: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [authHint, setAuthHint] = useState<string | null>(null);

  const clearAuthHint = useCallback(() => setAuthHint(null), []);

  const loadProfile = useCallback(async () => {
    const { data } = await supabaseAuditcore.auth.getSession();
    if (!data.session) {
      setUser(null);
      setAuthHint(null);
      return;
    }
    try {
      setUser(await api.me());
      setAuthHint(null);
    } catch (err) {
      try {
        const fallbackUser = await loadProfileFromSupabase();
        setUser(fallbackUser);
        setAuthHint(PREVIEW_BACKEND_HELP);
      } catch {
        await supabaseAuditcore.auth.signOut();
        setUser(null);
        setAuthHint(err instanceof Error ? err.message : null);
      }
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
    clearAuthHint();
    try {
      const tokens = await api.login(email, password);
      await supabaseAuditcore.auth.setSession({
        access_token: tokens.access_token,
        refresh_token: tokens.refresh_token ?? "",
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      if (/محاولات|قفل|غير صحيحة/.test(msg)) throw new Error(msg);

      try {
        const { error } = await supabaseAuditcore.auth.signInWithPassword({ email, password });
        if (error) {
          throw new Error(
            /invalid|credentials|password/i.test(error.message)
              ? "البريد الإلكتروني أو كلمة المرور غير صحيحة"
              : error.message,
          );
        }
      } catch (supabaseErr) {
        const fallbackMsg = supabaseErr instanceof Error ? supabaseErr.message : "";
        if (/Failed to fetch|fetch/i.test(fallbackMsg)) {
          throw new Error(
            "تعذّر الاتصال بخدمة المصادقة في وضع المعاينة. تأكد من ضبط مفاتيح Supabase في Lovable أو شغّل الخلفية محليًا عبر ./preview-backend.sh أو ./setup.sh.",
          );
        }
        throw supabaseErr;
      }
    }

    try {
      const me = await api.me();
      setUser(me);
      setAuthHint(null);
      return me;
    } catch {
      try {
        const fallbackUser = await loadProfileFromSupabase();
        setUser(fallbackUser);
        setAuthHint(PREVIEW_BACKEND_HELP);
        return fallbackUser;
      } catch (fallbackErr) {
        throw fallbackErr instanceof Error
          ? fallbackErr
          : new PreviewBackendUnavailableError();
      }
    }
  }, [clearAuthHint]);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* ignore */
    }
    await supabaseAuditcore.auth.signOut();
    setUser(null);
    setAuthHint(null);
  }, []);

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
    <AuthContext.Provider value={{ user, loading, authHint, login, logout, refresh, clearAuthHint }}>
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
