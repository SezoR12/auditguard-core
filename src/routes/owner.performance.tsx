import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { RequireRole } from "@/components/RequireRole";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { api, type AuditorPerformanceRow } from "@/lib/api";

export const Route = createFileRoute("/owner/performance")({
  head: () => ({ meta: [{ title: "أداء المدققين — AuditCore" }] }),
  component: () => (
    <RequireRole allow={["owner", "gm", "admin", "appowner"]}>
      <OwnerPerformancePage />
    </RequireRole>
  ),
});

function effColor(score: number): string {
  if (score >= 80) return "text-green-600";
  if (score >= 50) return "text-yellow-600";
  return "text-destructive";
}

function OwnerPerformancePage() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();

  const [rows, setRows] = useState<AuditorPerformanceRow[]>([]);
  const [loadingRows, setLoadingRows] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) void navigate({ to: "/login" });
  }, [user, loading, navigate]);

  const reload = useCallback(async () => {
    setLoadingRows(true);
    setError(null);
    try {
      setRows(await api.auditorPerformance());
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر تحميل بيانات الأداء");
    } finally {
      setLoadingRows(false);
    }
  }, []);

  useEffect(() => {
    if (user) void reload();
  }, [user, reload]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-muted-foreground">جارٍ التحميل...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background px-6 py-8" dir="rtl">
      <div className="mx-auto max-w-4xl">
        <header className="flex items-center justify-between border-b border-border pb-4">
          <div>
            <h1 className="text-2xl font-bold text-foreground">أداء المدققين</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              ملخص اليوم — المهام المنجزة والمتأخرة والنقاط السلبية
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              to="/owner"
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
            >
              لوحة المالك
            </Link>
            <button
              onClick={logout}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
            >
              خروج
            </button>
          </div>
        </header>

        {error && (
          <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-right text-sm text-destructive">
            {error}
          </div>
        )}

        <section className="mt-6 overflow-hidden rounded-xl border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold text-foreground">جدول الأداء اليومي</h2>
            <button
              onClick={() => void reload()}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              تحديث
            </button>
          </div>

          {loadingRows ? (
            <p className="px-4 py-8 text-center text-sm text-muted-foreground">جارٍ التحميل...</p>
          ) : rows.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-muted-foreground">
              لا يوجد مدققون لعرضهم
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-right text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-muted-foreground">
                    <th className="px-4 py-2 font-medium">المدقق</th>
                    <th className="px-4 py-2 font-medium">المنجزة اليوم</th>
                    <th className="px-4 py-2 font-medium">المتأخرة</th>
                    <th className="px-4 py-2 font-medium">النقاط السلبية</th>
                    <th className="px-4 py-2 font-medium">مؤشر الكفاءة</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.auditor_id} className="border-b border-border/50 last:border-0">
                      <td className="px-4 py-3 text-foreground">{r.full_name}</td>
                      <td className="px-4 py-3 text-green-600">{r.tasks_completed_today}</td>
                      <td className="px-4 py-3 text-destructive">{r.tasks_delayed}</td>
                      <td className="px-4 py-3 text-yellow-600">{r.demerit_points}</td>
                      <td className={["px-4 py-3 font-semibold", effColor(r.efficiency_score)].join(" ")}>
                        {r.efficiency_score.toFixed(1)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
