import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { supabaseAuditcore } from "@/lib/supabaseClient";
import { api, ApiError, type CurrentUser } from "@/lib/api";
import { loadProfileFromSupabase, PREVIEW_BACKEND_HELP, PreviewBackendUnavailableError } from "@/lib/authPreview";

/** Console breadcrumb so each login step (and its status code) is visible in
 *  devtools. Prefixed for easy filtering. */
function authLog(step: string, info?: unknown) {
  if (info instanceof ApiError) {
    // eslint-disable-next-line no-console
    console.warn(`[auth] ${step}`, {
      status: info.status,
      path: info.path,
      detail: info.detail,
      isNetworkError: info.isNetworkError,
    });
  } else if (info !== undefined) {
    // eslint-disable-next-line no-console
    console.info(`[auth] ${step}`, info);
  } else {
    // eslint-disable-next-line no-console
    console.info(`[auth] ${step}`);
  }
}

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

  const GUEST_USER: CurrentUser = {
    id: "00000000-0000-0000-0000-000000000000",
    email: "guest@auditcore.local",
    full_name: "زائر (وضع بدون تسجيل دخول)",
    role: "owner",
    company_id: "00000000-0000-0000-0000-000000000000",
    branch_id: null,
    is_active: true,
  };

  const loadProfile = useCallback(async () => {
    const { data } = await supabaseAuditcore.auth.getSession();
    if (!data.session) {
      // Credential-less access: synthesize an owner-level guest profile so the
      // app is fully navigable without signing in.
      setUser(GUEST_USER);
      setAuthHint(null);
      return;
    }
    try {
      setUser(await api.me());
      setAuthHint(null);
      authLog("loadProfile: /auth/me ok");
    } catch (err) {
      authLog("loadProfile: /auth/me failed → Supabase fallback", err);
      try {
        const fallbackUser = await loadProfileFromSupabase();
        setUser(fallbackUser);
        setAuthHint(PREVIEW_BACKEND_HELP);
        authLog("loadProfile: Supabase fallback ok", { role: fallbackUser.role });
      } catch (fallbackErr) {
        authLog("loadProfile: Supabase fallback failed → guest mode", fallbackErr);
        setUser(GUEST_USER);
        setAuthHint(null);
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
    // STEP 1 — obtain a session. Prefer the rate-limited backend proxy; fall
    // back to direct Supabase auth when the proxy is unreachable.
    try {
      authLog("login step 1: POST /auth/login (rate-limit proxy)");
      const tokens = await api.login(email, password);
      await supabaseAuditcore.auth.setSession({
        access_token: tokens.access_token,
        refresh_token: tokens.refresh_token ?? "",
      });
      authLog("login step 1: proxy ok, session set");
    } catch (err) {
      authLog("login step 1: proxy failed", err);
      // A real auth rejection from the proxy (bad creds / lockout) must surface
      // as-is — do NOT fall back to a second password attempt.
      if (err instanceof ApiError && (err.status === 401 || err.status === 429)) {
        throw new Error(err.detail);
      }
      const msg = err instanceof Error ? err.message : "";
      if (/محاولات|قفل|غير صحيحة/.test(msg)) throw new Error(msg);

      // STEP 1b — proxy unreachable (network/5xx): try Supabase directly.
      try {
        authLog("login step 1b: direct Supabase signInWithPassword");
        const { error } = await supabaseAuditcore.auth.signInWithPassword({ email, password });
        if (error) {
          authLog("login step 1b: Supabase rejected", error.message);
          throw new Error(
            /invalid|credentials|password/i.test(error.message)
              ? "البريد الإلكتروني أو كلمة المرور غير صحيحة"
              : error.message,
          );
        }
        authLog("login step 1b: Supabase session ok");
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

    // STEP 2 — resolve the profile. /auth/me failure is RECOVERABLE: read the
    // profile from Supabase and continue (preview / backend-down mode).
    try {
      authLog("login step 2: GET /auth/me");
      const me = await api.me();
      setUser(me);
      setAuthHint(null);
      authLog("login step 2: /auth/me ok", { role: me.role });
      return me;
    } catch (meErr) {
      authLog("login step 2: /auth/me failed → Supabase fallback", meErr);
      try {
        const fallbackUser = await loadProfileFromSupabase();
        setUser(fallbackUser);
        setAuthHint(PREVIEW_BACKEND_HELP);
        authLog("login step 2: Supabase profile fallback ok", { role: fallbackUser.role });
        return fallbackUser;
      } catch (fallbackErr) {
        authLog("login step 2: Supabase profile fallback failed", fallbackErr);
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
