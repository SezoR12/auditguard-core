import { useEffect, type ReactNode } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useAuth } from "@/hooks/useAuth";

interface Props {
  expectedRole: "owner" | "gm" | "manager" | "auditor";
  title: string;
  /** Optional extra content rendered inside the dashboard main panel. */
  children?: ReactNode;
}

export function RoleDashboard({ expectedRole, title, children }: Props) {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!loading && !user) void navigate({ to: "/login" });
  }, [user, loading, navigate]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-muted-foreground">جارٍ التحميل...</p>
      </div>
    );
  }

  if (user.role !== expectedRole) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4" dir="rtl">
        <div className="max-w-md rounded-xl border border-destructive/40 bg-destructive/5 p-6 text-right">
          <h2 className="text-lg font-semibold text-destructive">ليس لديك الصلاحية</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            دورك الحالي ({user.role}) لا يسمح بالوصول إلى هذه الصفحة.
          </p>
          <button
            onClick={logout}
            className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            تسجيل الخروج
          </button>
        </div>
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
