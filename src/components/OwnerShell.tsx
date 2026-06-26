import { Link, useNavigate } from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";
import { useAuth } from "@/hooks/useAuth";

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

  useEffect(() => {
    if (!loading && !user) void navigate({ to: "/login" });
  }, [user, loading, navigate]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-muted-foreground">جاري تحليل البيانات...</p>
      </div>
    );
  }

  if (!OWNER_ROLES.includes(user.role)) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4" dir="rtl">
        <div className="max-w-md rounded-xl border border-destructive/40 bg-destructive/5 p-6 text-right">
          <h2 className="text-lg font-semibold text-destructive">ليس لديك الصلاحية</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            هذه الصفحة مخصصة للمالك والإدارة فقط.
          </p>
        </div>
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
            <Link to="/owner" className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent">
              الرئيسية
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
