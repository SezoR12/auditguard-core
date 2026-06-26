import { Link, useNavigate } from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";
import { useAuth, roleHomePath } from "@/hooks/useAuth";
import { NotificationBell } from "@/components/NotificationBell";

const OWNER_ROLES = ["owner", "gm", "admin", "appowner"];

export function OwnerShell({
  title,
  subtitle,
  onRefresh,
  children,
}: {
  title: string;
  subtitle?: string;
  onRefresh?: () => void;
  children: ReactNode;
}) {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();

  const allowed = !!user && OWNER_ROLES.includes(user.role);

  useEffect(() => {
    if (loading) return; // wait for /auth/me to resolve
    if (!user) {
      void navigate({ to: "/login" });
      return;
    }
    // Wrong role → redirect to the user's own dashboard, not a dead end.
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
    <div className="min-h-screen bg-background px-6 py-8" dir="rtl">
      <div className="mx-auto max-w-6xl">
        <header className="flex items-center justify-between border-b border-border pb-4">
          <div>
            <h1 className="text-2xl font-bold text-foreground">{title}</h1>
            {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
          </div>
          <div className="flex items-center gap-2">
            <NotificationBell />
            <Link to="/owner" className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent">
              الرئيسية
            </Link>
            <Link to="/owner/custom-reports" className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent">
              التقارير المخصصة
            </Link>
            {onRefresh && (
              <button onClick={onRefresh} className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent">
                تحديث
              </button>
            )}
            <button onClick={logout} className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent">
              خروج
            </button>
          </div>
        </header>
        <main className="mt-6">{children}</main>
      </div>
    </div>
  );
}
