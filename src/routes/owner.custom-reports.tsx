import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { OwnerShell } from "@/components/OwnerShell";
import { api, type CustomReportItem, type ReportRequestItem } from "@/lib/api";
import { downloadAuthed } from "@/lib/download";
import { formatDate } from "@/lib/format";

export const Route = createFileRoute("/owner/custom-reports")({
  head: () => ({ meta: [{ title: "التقارير المخصصة — AuditCore" }] }),
  component: CustomReportsPage,
});

function CustomReportsPage() {
  const [reports, setReports] = useState<CustomReportItem[]>([]);
  const [requests, setRequests] = useState<ReportRequestItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [requirements, setRequirements] = useState("");

  const reload = useCallback(async () => {
    try {
      const [r, q] = await Promise.all([api.customReports(), api.myReportRequests()]);
      setReports(r);
      setRequests(q);
    } catch (e) {
      setError(e instanceof Error ? e.message : "خطأ");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function submitRequest() {
    if (!title.trim()) return;
    setError(null);
    setInfo(null);
    try {
      await api.createReportRequest({ title, requirements: requirements || undefined });
      setInfo("تم إرسال طلب التقرير المخصص. سيتواصل معك فريق AuditCore.");
      setTitle("");
      setRequirements("");
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر إرسال الطلب");
    }
  }

  async function generate(r: CustomReportItem) {
    setError(null);
    try {
      await downloadAuthed(api.generateCustomReportUrl(r.id), `${r.name}.pdf`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر توليد التقرير");
    }
  }

  return (
    <OwnerShell title="التقارير المخصصة" subtitle="اطلب تقارير تحليلية مخصصة وولّد نسخ PDF ببياناتك الحية" onRefresh={reload}>
      {info && <div className="mb-4 rounded-md border border-green-500/40 bg-green-500/10 px-4 py-2 text-sm text-green-700">{info}</div>}
      {error && <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">{error}</div>}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Request a custom report */}
        <section className="rounded-xl border border-border bg-card p-5">
          <h2 className="mb-3 text-sm font-semibold text-foreground">طلب تقرير تحليلي مخصص</h2>
          <label className="mb-1 block text-xs text-muted-foreground">عنوان التقرير</label>
          <input value={title} onChange={(e) => setTitle(e.target.value)} className="mb-3 w-full rounded-md border border-input bg-background px-3 py-2 text-right text-sm" placeholder="مثال: تقرير العائد الإيجاري الشهري" />
          <label className="mb-1 block text-xs text-muted-foreground">المتطلبات</label>
          <textarea value={requirements} onChange={(e) => setRequirements(e.target.value)} rows={3} className="mb-3 w-full rounded-md border border-input bg-background px-3 py-2 text-right text-sm" placeholder="اشرح ما تريد رؤيته في التقرير" />
          <button onClick={() => void submitRequest()} className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90">طلب تقرير تحليلي مخصص</button>

          {requests.length > 0 && (
            <div className="mt-5">
              <h3 className="mb-2 text-xs font-semibold text-muted-foreground">طلباتي</h3>
              <ul className="space-y-1 text-sm">
                {requests.map((r) => (
                  <li key={r.id} className="flex items-center justify-between rounded-md border border-border/50 px-3 py-1.5">
                    <span>{r.title}</span>
                    <span className="rounded-full bg-muted px-2 py-0.5 text-xs">{r.status}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        {/* Deployed custom reports library */}
        <section className="rounded-xl border border-border bg-card p-5">
          <h2 className="mb-3 text-sm font-semibold text-foreground">مكتبة التقارير المخصصة</h2>
          {reports.length === 0 ? (
            <p className="text-sm text-muted-foreground">لا توجد تقارير منشورة بعد. اطلب تقريراً مخصصاً ليظهر هنا.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {reports.map((r) => (
                <li key={r.id} className="flex items-center justify-between rounded-md border border-border/60 px-3 py-2">
                  <div>
                    <div className="text-foreground">{r.name}</div>
                    <div className="text-xs text-muted-foreground" dir="ltr">{formatDate(r.deployed_at)}</div>
                  </div>
                  <button onClick={() => void generate(r)} className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90">توليد PDF</button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </OwnerShell>
  );
}
