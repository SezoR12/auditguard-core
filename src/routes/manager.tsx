import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { RequireRole } from "@/components/RequireRole";
import { api, type WidgetDef } from "@/lib/api";
import { formatIQD } from "@/lib/format";

export const Route = createFileRoute("/manager")({
  head: () => ({ meta: [{ title: "لوحة المدير — AuditCore" }] }),
  component: () => (
    <RequireRole allow={["manager", "admin", "appowner"]}>
      <ManagerDashboard />
    </RequireRole>
  ),
});

const STORAGE_KEY = "auditcore.manager.widgets";
const DEFAULT_WIDGETS = ["open_tasks", "pending_corrections", "dept_quality_index"];

function WidgetCard({
  def,
  onRemove,
  onMoveLeft,
  onMoveRight,
}: {
  def: WidgetDef;
  onRemove: () => void;
  onMoveLeft: () => void;
  onMoveRight: () => void;
}) {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await api.managerWidget(def.key));
    } catch (e) {
      setError(e instanceof Error ? e.message : "خطأ");
    }
  }, [def.key]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">{def.label}</h3>
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <button onClick={onMoveRight} title="يمين" className="px-1 hover:text-foreground">→</button>
          <button onClick={onMoveLeft} title="يسار" className="px-1 hover:text-foreground">←</button>
          <button onClick={onRemove} title="إزالة" className="px-1 text-destructive hover:opacity-80">✕</button>
        </div>
      </div>
      {error ? (
        <p className="text-xs text-destructive">{error}</p>
      ) : !data ? (
        <p className="text-xs text-muted-foreground">جاري التحميل...</p>
      ) : (
        <WidgetBody widgetKey={def.key} data={data} />
      )}
    </div>
  );
}

function WidgetBody({ widgetKey, data }: { widgetKey: string; data: Record<string, unknown> }) {
  if (widgetKey === "open_tasks") {
    return (
      <div className="flex gap-6">
        <div><div className="text-2xl font-bold text-blue-600">{Number(data.open_tasks ?? 0)}</div><div className="text-xs text-muted-foreground">مفتوحة</div></div>
        <div><div className="text-2xl font-bold text-destructive">{Number(data.overdue ?? 0)}</div><div className="text-xs text-muted-foreground">متأخرة</div></div>
      </div>
    );
  }
  if (widgetKey === "budget_status") {
    return <div className="text-2xl font-bold text-red-600">{formatIQD(Number(data.total_waste_iqd ?? 0))}</div>;
  }
  if (widgetKey === "dept_quality_index") {
    return <div className="text-2xl font-bold text-blue-600">{Number(data.quality_index ?? 0)}%</div>;
  }
  if (widgetKey === "pending_corrections") {
    return <div className="text-2xl font-bold text-amber-600">{Number(data.pending_corrections ?? 0)}</div>;
  }
  if (widgetKey === "team_performance") {
    const team = (data.team as Array<{ auditor: string; completed: number; delayed: number; efficiency: number }>) ?? [];
    return team.length === 0 ? (
      <p className="text-xs text-muted-foreground">لا يوجد فريق</p>
    ) : (
      <table className="w-full text-right text-xs">
        <thead><tr className="text-muted-foreground"><th className="py-1">المدقق</th><th>منجز</th><th>متأخر</th><th>كفاءة</th></tr></thead>
        <tbody>
          {team.map((m, i) => (
            <tr key={i} className="border-t border-border/40"><td className="py-1">{m.auditor}</td><td>{m.completed}</td><td>{m.delayed}</td><td>{m.efficiency}%</td></tr>
          ))}
        </tbody>
      </table>
    );
  }
  return <pre className="text-xs" dir="ltr">{JSON.stringify(data, null, 2)}</pre>;
}

function ManagerDashboard() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();
  const [available, setAvailable] = useState<WidgetDef[]>([]);
  const [active, setActive] = useState<string[]>([]);
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    if (!loading && !user) void navigate({ to: "/login" });
  }, [user, loading, navigate]);

  useEffect(() => {
    void api.managerWidgets().then((d) => setAvailable(d.widgets)).catch(() => {});
    const saved = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
    setActive(saved ? JSON.parse(saved) : DEFAULT_WIDGETS);
  }, []);

  useEffect(() => {
    if (active.length) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(active));
  }, [active]);

  const byKey = useMemo(() => Object.fromEntries(available.map((w) => [w.key, w])), [available]);

  function move(idx: number, delta: number) {
    setActive((prev) => {
      const next = [...prev];
      const j = idx + delta;
      if (j < 0 || j >= next.length) return prev;
      [next[idx], next[j]] = [next[j], next[idx]];
      return next;
    });
  }

  if (loading || !user) {
    return <div className="flex min-h-screen items-center justify-center bg-background"><p className="text-muted-foreground">جاري التحميل...</p></div>;
  }

  return (
    <div className="min-h-screen bg-background px-6 py-8" dir="rtl">
      <div className="mx-auto max-w-6xl">
        <header className="flex items-center justify-between border-b border-border pb-4">
          <div>
            <h1 className="text-2xl font-bold text-foreground">لوحة المدير</h1>
            <p className="mt-1 text-sm text-muted-foreground">مرحباً {user.full_name} — لوحة قابلة للتخصيص (بيانات قسمك فقط)</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setShowModal(true)} className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90">إضافة عنصر</button>
            <button onClick={logout} className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent">خروج</button>
          </div>
        </header>

        <main className="mt-6">
          {active.length === 0 ? (
            <p className="py-16 text-center text-sm text-muted-foreground">لا توجد عناصر. اضغط «إضافة عنصر» لبدء بناء لوحتك.</p>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {active.map((key, idx) =>
                byKey[key] ? (
                  <WidgetCard
                    key={key}
                    def={byKey[key]}
                    onRemove={() => setActive((p) => p.filter((k) => k !== key))}
                    onMoveLeft={() => move(idx, 1)}
                    onMoveRight={() => move(idx, -1)}
                  />
                ) : null
              )}
            </div>
          )}
        </main>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setShowModal(false)}>
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-5" dir="rtl" onClick={(e) => e.stopPropagation()}>
            <h2 className="mb-3 text-sm font-semibold text-foreground">اختر العناصر</h2>
            <div className="space-y-2">
              {available.map((w) => {
                const on = active.includes(w.key);
                return (
                  <label key={w.key} className="flex items-center justify-between rounded-md border border-border/60 px-3 py-2 text-sm">
                    <span>{w.label}</span>
                    <input
                      type="checkbox"
                      checked={on}
                      onChange={(e) =>
                        setActive((p) => (e.target.checked ? [...p, w.key] : p.filter((k) => k !== w.key)))
                      }
                    />
                  </label>
                );
              })}
            </div>
            <button onClick={() => setShowModal(false)} className="mt-4 w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90">تم</button>
          </div>
        </div>
      )}
    </div>
  );
}
