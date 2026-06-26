import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { RequireRole } from "@/components/RequireRole";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { api, type TaskColor, type TaskItem } from "@/lib/api";

export const Route = createFileRoute("/auditor/tasks")({
  head: () => ({ meta: [{ title: "مهامي اليومية — AuditCore" }] }),
  component: () => (
    <RequireRole allow={["auditor", "admin", "appowner"]}>
      <TasksPage />
    </RequireRole>
  ),
});

const TYPE_LABELS: Record<string, string> = {
  document_review: "تدقيق مستندات",
  reconciliation: "مطابقة",
  investigation: "تحقيق",
  field_visit: "زيارة ميدانية",
  other: "أخرى",
};

const STATUS_LABELS: Record<TaskItem["status"], string> = {
  pending: "قيد الانتظار",
  in_progress: "قيد التنفيذ",
  completed: "منجزة",
  overdue: "متأخرة",
};

const COLOR_ROW: Record<TaskColor, string> = {
  green: "border-r-4 border-green-500",
  yellow: "border-r-4 border-yellow-500",
  red: "border-r-4 border-destructive",
};

function formatRemaining(seconds: number | null, status: TaskItem["status"]): string {
  if (status === "completed") return "—";
  if (seconds === null) return "—";
  const overdue = seconds < 0;
  const abs = Math.abs(seconds);
  const h = Math.floor(abs / 3600);
  const m = Math.floor((abs % 3600) / 60);
  const s = abs % 60;
  const txt = `${h}س ${m.toString().padStart(2, "0")}د ${s.toString().padStart(2, "0")}ث`;
  return overdue ? `متأخرة بـ ${txt}` : txt;
}

function TasksPage() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();

  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loadingTasks, setLoadingTasks] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0); // drives the live countdown

  useEffect(() => {
    if (!loading && !user) void navigate({ to: "/login" });
  }, [user, loading, navigate]);

  const reload = useCallback(async () => {
    setLoadingTasks(true);
    setError(null);
    try {
      setTasks(await api.myTasks());
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر تحميل المهام");
    } finally {
      setLoadingTasks(false);
    }
  }, []);

  useEffect(() => {
    if (user) void reload();
  }, [user, reload]);

  // Live countdown: re-render every second (locally derive remaining time).
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  async function onComplete(id: string) {
    try {
      await api.completeTask(id);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر إنجاز المهمة");
    }
  }

  // Derive live remaining seconds from sla_deadline so the timer counts down.
  const liveTasks = useMemo(() => {
    void tick;
    const now = Date.now();
    return tasks.map((t) => {
      let remaining = t.time_remaining_seconds;
      let color: TaskColor = t.time_color;
      if (t.status !== "completed" && t.sla_deadline) {
        remaining = Math.round((new Date(t.sla_deadline).getTime() - now) / 1000);
        if (remaining <= 0) color = "red";
        else if (t.created_at) {
          const total =
            (new Date(t.sla_deadline).getTime() - new Date(t.created_at).getTime()) / 1000;
          color = total > 0 && remaining / total < 0.5 ? "yellow" : "green";
        }
      }
      return { ...t, _remaining: remaining, _color: color };
    });
  }, [tasks, tick]);

  const summary = useMemo(() => {
    const done = tasks.filter((t) => t.status === "completed").length;
    const delayed = tasks.filter((t) => t.status === "overdue").length;
    const demerits = tasks.reduce((sum, t) => sum + t.demerit_points, 0);
    return { done, delayed, demerits };
  }, [tasks]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-muted-foreground">جارٍ التحميل...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background px-6 py-8" dir="rtl">
      <div className="mx-auto max-w-5xl">
        <header className="flex items-center justify-between border-b border-border pb-4">
          <div>
            <h1 className="text-2xl font-bold text-foreground">مهامي اليومية</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              مرحباً {user.full_name} — تابع مهامك والوقت المتبقي لكل منها
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              to="/auditor"
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
            >
              لوحة المدقق
            </Link>
            <button
              onClick={logout}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
            >
              خروج
            </button>
          </div>
        </header>

        {/* Summary */}
        <div className="mt-6 grid grid-cols-3 gap-3">
          <div className="rounded-xl border border-border bg-card p-4 text-center">
            <div className="text-2xl font-bold text-green-600">{summary.done}</div>
            <div className="mt-1 text-xs text-muted-foreground">المهام المنجزة</div>
          </div>
          <div className="rounded-xl border border-border bg-card p-4 text-center">
            <div className="text-2xl font-bold text-destructive">{summary.delayed}</div>
            <div className="mt-1 text-xs text-muted-foreground">المتأخرة</div>
          </div>
          <div className="rounded-xl border border-border bg-card p-4 text-center">
            <div className="text-2xl font-bold text-yellow-600">{summary.demerits}</div>
            <div className="mt-1 text-xs text-muted-foreground">النقاط السلبية</div>
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-right text-sm text-destructive">
            {error}
          </div>
        )}

        {/* Tasks table */}
        <section className="mt-6 overflow-hidden rounded-xl border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold text-foreground">مهام اليوم</h2>
            <button
              onClick={() => void reload()}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              تحديث
            </button>
          </div>

          {loadingTasks ? (
            <p className="px-4 py-8 text-center text-sm text-muted-foreground">جارٍ التحميل...</p>
          ) : liveTasks.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-muted-foreground">
              لا توجد مهام لهذا اليوم
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-right text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-muted-foreground">
                    <th className="px-4 py-2 font-medium">المهمة</th>
                    <th className="px-4 py-2 font-medium">النوع</th>
                    <th className="px-4 py-2 font-medium">الحالة</th>
                    <th className="px-4 py-2 font-medium">وقت التسليم</th>
                    <th className="px-4 py-2 font-medium">الوقت المتبقي</th>
                    <th className="px-4 py-2 font-medium">إجراء</th>
                  </tr>
                </thead>
                <tbody>
                  {liveTasks.map((t) => (
                    <tr
                      key={t.id}
                      className={["border-b border-border/50 last:border-0", COLOR_ROW[t._color]].join(" ")}
                    >
                      <td className="px-4 py-3 text-foreground">
                        {t.is_critical && <span className="ml-1 text-destructive" title="حرجة">★</span>}
                        {t.title}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {TYPE_LABELS[t.task_type] ?? t.task_type}
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-foreground">
                          {STATUS_LABELS[t.status]}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground" dir="ltr">
                        {t.sla_deadline
                          ? new Date(t.sla_deadline).toLocaleString("ar-IQ", {
                              month: "2-digit",
                              day: "2-digit",
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : "—"}
                      </td>
                      <td
                        className={[
                          "px-4 py-3 font-medium",
                          t._color === "red"
                            ? "text-destructive"
                            : t._color === "yellow"
                              ? "text-yellow-600"
                              : "text-green-600",
                        ].join(" ")}
                      >
                        {formatRemaining(t._remaining, t.status)}
                      </td>
                      <td className="px-4 py-3">
                        {t.status === "completed" ? (
                          <span className="text-xs text-green-600">✓ منجزة</span>
                        ) : (
                          <button
                            onClick={() => void onComplete(t.id)}
                            className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90"
                          >
                            إنجاز
                          </button>
                        )}
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
