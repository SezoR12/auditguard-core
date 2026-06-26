import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import {
  api,
  type CriteriaModule,
  type ReportRequestItem,
  type ReportTemplateItem,
} from "@/lib/api";
import { downloadAuthed } from "@/lib/download";
import { RequireRole } from "@/components/RequireRole";

export const Route = createFileRoute("/appowner")({
  head: () => ({ meta: [{ title: "بانل مالك التطبيق — AuditCore" }] }),
  component: () => (
    <RequireRole allow={["appowner", "admin"]}>
      <AppOwnerPanel />
    </RequireRole>
  ),
});

type Block =
  | { type: "text"; content: string }
  | { type: "metric"; binding: string; label: string }
  | { type: "table"; source: string; columns: string[] }
  | { type: "chart"; source: string }
  | { type: "image"; placeholder: string };

const ROLES_OK = ["appowner", "admin"];

function AppOwnerPanel() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();

  const [modules, setModules] = useState<CriteriaModule[]>([]);
  const [templates, setTemplates] = useState<ReportTemplateItem[]>([]);
  const [requests, setRequests] = useState<ReportRequestItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  // Builder state
  const [name, setName] = useState("قالب جديد");
  const [sectors, setSectors] = useState<string[]>([]);
  const [blocks, setBlocks] = useState<Block[]>([
    { type: "text", content: "ملخص الأداء" },
    { type: "table", source: "waste_map_items", columns: ["department", "category", "amount_iqd", "status"] },
    { type: "chart", source: "waste_by_department" },
  ]);

  useEffect(() => {
    if (!loading && !user) void navigate({ to: "/login" });
  }, [user, loading, navigate]);

  const reload = useCallback(async () => {
    try {
      const [m, t, r] = await Promise.all([api.templateCriteria(), api.listTemplates(), api.adminReportRequests()]);
      setModules(m.modules);
      setTemplates(t);
      setRequests(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "خطأ");
    }
  }, []);

  useEffect(() => {
    if (user) void reload();
  }, [user, reload]);

  const sectorMetrics = useMemo(
    () => modules.filter((m) => sectors.includes(m.sector)).flatMap((m) => m.metrics),
    [modules, sectors],
  );

  const config = useMemo(() => ({ title: name, blocks }), [name, blocks]);

  async function saveTemplate() {
    setError(null);
    setInfo(null);
    try {
      const t = await api.createTemplate({ name, sectors, config, is_published: true });
      setInfo(`تم حفظ القالب: ${t.name}`);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر الحفظ");
    }
  }

  async function deploy(reqId: string, templateId: string) {
    const price = prompt("سعر التقرير (د.ع):", "250000");
    try {
      await api.deployTemplate(reqId, { template_id: templateId, price_iqd: price ? Number(price) : undefined });
      setInfo("تم نشر القالب إلى العميل.");
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر النشر");
    }
  }

  if (loading || !user) return <div className="flex min-h-screen items-center justify-center text-muted-foreground">جاري التحميل...</div>;
  if (!ROLES_OK.includes(user.role)) {
    return <div className="flex min-h-screen items-center justify-center" dir="rtl"><p className="text-destructive">هذه الصفحة لمالك التطبيق فقط.</p></div>;
  }

  return (
    <div className="min-h-screen bg-background px-6 py-8" dir="rtl">
      <div className="mx-auto max-w-6xl">
        <header className="flex items-center justify-between border-b border-border pb-4">
          <h1 className="text-2xl font-bold text-foreground">بانل مالك التطبيق — منشئ التقارير</h1>
          <button onClick={logout} className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent">خروج</button>
        </header>

        {info && <div className="mt-4 rounded-md border border-green-500/40 bg-green-500/10 px-4 py-2 text-sm text-green-700">{info}</div>}
        {error && <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">{error}</div>}

        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Builder */}
          <section className="rounded-xl border border-border bg-card p-5">
            <h2 className="mb-3 text-sm font-semibold text-foreground">منشئ القالب (بدون كود)</h2>
            <label className="mb-1 block text-xs text-muted-foreground">اسم القالب</label>
            <input value={name} onChange={(e) => setName(e.target.value)} className="mb-4 w-full rounded-md border border-input bg-background px-3 py-2 text-right text-sm" />

            <div className="mb-4">
              <div className="mb-1 text-xs text-muted-foreground">القطاعات (تضيف مؤشرات خاصة)</div>
              <div className="flex flex-wrap gap-2">
                {modules.map((m) => (
                  <label key={m.sector} className="flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-xs">
                    <input
                      type="checkbox"
                      checked={sectors.includes(m.sector)}
                      onChange={(e) => setSectors((p) => (e.target.checked ? [...p, m.sector] : p.filter((x) => x !== m.sector)))}
                    />
                    {m.label}
                  </label>
                ))}
              </div>
            </div>

            <div className="mb-3 text-xs text-muted-foreground">العناصر</div>
            <div className="space-y-2">
              {blocks.map((b, i) => (
                <div key={i} className="flex items-center justify-between rounded-md border border-border/60 px-3 py-2 text-sm">
                  <span>{blockLabel(b)}</span>
                  <button onClick={() => setBlocks((p) => p.filter((_, j) => j !== i))} className="text-destructive">✕</button>
                </div>
              ))}
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              <button onClick={() => setBlocks((p) => [...p, { type: "text", content: "نص جديد" }])} className="rounded-md border border-input px-2 py-1 text-xs hover:bg-accent">+ نص</button>
              <button onClick={() => setBlocks((p) => [...p, { type: "table", source: "waste_map_items", columns: ["department", "category", "amount_iqd", "status"] }])} className="rounded-md border border-input px-2 py-1 text-xs hover:bg-accent">+ جدول</button>
              <button onClick={() => setBlocks((p) => [...p, { type: "chart", source: "waste_by_department" }])} className="rounded-md border border-input px-2 py-1 text-xs hover:bg-accent">+ رسم بياني</button>
              <button onClick={() => setBlocks((p) => [...p, { type: "image", placeholder: "صورة" }])} className="rounded-md border border-input px-2 py-1 text-xs hover:bg-accent">+ صورة</button>
              {sectorMetrics.map((m) => (
                <button key={m.key} onClick={() => setBlocks((p) => [...p, { type: "metric", binding: m.key, label: m.label }])} className="rounded-md border border-blue-400/50 px-2 py-1 text-xs text-blue-600 hover:bg-accent">+ {m.label}</button>
              ))}
            </div>

            <button onClick={() => void saveTemplate()} className="mt-5 w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90">حفظ القالب</button>
          </section>

          {/* Templates + CRaaS inbox */}
          <section className="space-y-6">
            <div className="rounded-xl border border-border bg-card p-5">
              <h2 className="mb-3 text-sm font-semibold text-foreground">القوالب المحفوظة</h2>
              {templates.length === 0 ? <p className="text-xs text-muted-foreground">لا توجد قوالب</p> : (
                <ul className="space-y-2 text-sm">
                  {templates.map((t) => (
                    <li key={t.id} className="flex items-center justify-between rounded-md border border-border/60 px-3 py-2">
                      <span>{t.name} <span className="text-xs text-muted-foreground">v{t.version}</span></span>
                      <button onClick={() => void downloadAuthed(api.templatePreviewUrl(t.id), `${t.name}.pdf`).catch((e) => setError(String(e)))} className="text-xs text-blue-600 hover:underline">معاينة PDF</button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="rounded-xl border border-border bg-card p-5">
              <h2 className="mb-3 text-sm font-semibold text-foreground">طلبات التقارير (CRaaS)</h2>
              {requests.length === 0 ? <p className="text-xs text-muted-foreground">لا توجد طلبات</p> : (
                <ul className="space-y-2 text-sm">
                  {requests.map((r) => (
                    <li key={r.id} className="rounded-md border border-border/60 px-3 py-2">
                      <div className="flex items-center justify-between">
                        <span>{r.title}</span>
                        <span className="rounded-full bg-muted px-2 py-0.5 text-xs">{r.status}</span>
                      </div>
                      {r.requirements && <p className="mt-1 text-xs text-muted-foreground">{r.requirements}</p>}
                      {r.status !== "deployed" && templates.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {templates.map((t) => (
                            <button key={t.id} onClick={() => void deploy(r.id, t.id)} className="rounded-md bg-primary px-2 py-1 text-xs text-primary-foreground hover:opacity-90">نشر «{t.name}»</button>
                          ))}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function blockLabel(b: Block): string {
  switch (b.type) {
    case "text": return `نص: ${b.content}`;
    case "metric": return `مؤشر: ${b.label}`;
    case "table": return `جدول: ${b.source}`;
    case "chart": return `رسم بياني: ${b.source}`;
    case "image": return `صورة: ${b.placeholder}`;
  }
}
