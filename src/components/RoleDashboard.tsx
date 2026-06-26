import { useEffect, type ReactNode } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useAuth, roleHomePath } from "@/hooks/useAuth";

interface Props {
  expectedRole: "owner" | "gm" | "manager" | "auditor";
  title: string;
  /** Optional extra content rendered inside the dashboard main panel. */
  children?: ReactNode;
}

// Platform roles can view any role dashboard.
const PLATFORM = ["admin", "appowner"];

export function RoleDashboard({ expectedRole, title, children }: Props) {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();

  const allowed = !!user && (user.role === expectedRole || PLATFORM.includes(user.role));

  useEffect(() => {
    if (loading) return; // wait for /auth/me to resolve
    if (!user) {
      void navigate({ to: "/login" });
      return;
    }
    // Wrong role → send the user to THEIR own dashboard, not a dead end.
    if (!allowed) void navigate({ to: roleHomePath(user.role) });
  }, [user, loading, allowed, navigate]);

  if (loading || !user || !allowed) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background" dir="rtl">
        <p className="text-muted-foreground">جارٍ التحقق من الصلاحيات...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background px-6 py-10" dir="rtl">
      <div className="mx-auto max-w-3xl">
        <header className="flex items-center justify-between border-b border-border pb-4">
          <div>
            <h1 className="text-2xl font-bold text-foreground">{title}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              مرحباً {user.full_name} — دورك: {user.role}
            </p>
          </div>
          <button
            onClick={logout}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
          >
            خروج
          </button>
        </header>

        <main className="mt-8 rounded-xl border border-border bg-card p-6">
          {children ?? (
            <p className="text-sm text-muted-foreground">
              هذه صفحة تجريبية. المرحلة الأولى تتحقق فقط من توجيه الأدوار.
            </p>
          )}
        </main>
      </div>
    </div>
  );
}
