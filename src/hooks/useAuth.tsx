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
    const { error } = await supabaseAuditcore.auth.signInWithPassword({ email, password });
    if (error) {
      // Surface a normalized Arabic message for invalid creds.
      const msg = /invalid|credentials|password/i.test(error.message)
        ? "البريد الإلكتروني أو كلمة المرور غير صحيحة"
        : error.message;
      throw new Error(msg);
    }
    const me = await api.me();
    setUser(me);
    return me;
  }, []);

  const logout = useCallback(async () => {
    await supabaseAuditcore.auth.signOut();
    setUser(null);
  }, []);

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
