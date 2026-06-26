import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { OwnerShell } from "@/components/OwnerShell";
import {
  api,
  type AnomalyFinding,
  type CrossRefFinding,
  type DashLayer3,
} from "@/lib/api";
import { formatIQD, formatDate } from "@/lib/format";

interface Search {
  department?: string;
  severity?: string;
}

export const Route = createFileRoute("/owner/analytics")({
  validateSearch: (s: Record<string, unknown>): Search => ({
    department: typeof s.department === "string" ? s.department : undefined,
    severity: typeof s.severity === "string" ? s.severity : undefined,
  }),
  head: () => ({ meta: [{ title: "التحليلات — AuditCore" }] }),
  component: OwnerLayer3,
});

const SEV_LABELS: Record<string, string> = {
  low: "منخفض",
  medium: "متوسط",
  high: "عالٍ",
  critical: "حرج",
};
const SEV_COLOR: Record<string, string> = {
  low: "text-muted-foreground",
  medium: "text-amber-600",
  high: "text-orange-600",
  critical: "text-red-600",
};

function findingDocId(f: CrossRefFinding | AnomalyFinding): string | null {
  // details may carry a document_id for drill-down; not always present.
  const d = (f as unknown as { details?: Record<string, unknown> }).details;
  const v = d?.document_id;
  return typeof v === "string" ? v : null;
}

function OwnerLayer3() {
  const navigate = useNavigate();
  const search = Route.useSearch();
  const [data, setData] = useState<DashLayer3 | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [severity, setSeverity] = useState(search.severity ?? "");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.dashLayer3({ department: search.department, severity: severity || undefined }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "خطأ");
    } finally {
      setLoading(false);
    }
  }, [search.department, severity]);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <OwnerShell
      title="ملخص الذكاء الاصطناعي"
      subtitle={search.department ? `القسم: ${search.department}` : "التضاربات والشذوذ المكتشف"}
      onRefresh={load}
    >
      {loading && !data ? (
        <p className="py-16 text-center text-muted-foreground">جاري تحليل البيانات...</p>
      ) : error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-right text-sm text-destructive">{error}</div>
      ) : (
        <div className="space-y-6">
          {/* Narratives */}
          {data && data.narratives.length > 0 && (
            <section className="rounded-xl border border-blue-500/30 bg-blue-500/5 p-4">
              <h2 className="mb-2 text-sm font-semibold text-foreground">ملخص الذكاء الاصطناعي</h2>
              <ul className="space-y-2 text-sm text-foreground">
                {data.narratives.slice(0, 4).map((n, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-blue-600">•</span>
                    <span>{n.text}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Severity filter */}
          <div className="flex items-end gap-3">
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">الخطورة</label>
              <select
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-right text-sm"
              >
                <option value="">الكل</option>
                <option value="low">منخفض</option>
                <option value="medium">متوسط</option>
                <option value="high">عالٍ</option>
                <option value="critical">حرج</option>
              </select>
            </div>
          </div>

          {/* Cross-reference findings */}
          <section className="overflow-hidden rounded-xl border border-border bg-card">
            <h2 className="border-b border-border px-4 py-3 text-sm font-semibold text-foreground">التضاربات المكتشفة</h2>
            {(data?.cross_reference_findings ?? []).length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-muted-foreground">لا توجد تضاربات</p>
            ) : (
              <table className="w-full text-right text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-muted-foreground">
                    <th className="px-4 py-2 font-medium">النوع</th>
                    <th className="px-4 py-2 font-medium">الوصف</th>
                    <th className="px-4 py-2 font-medium">الفرق</th>
                    <th className="px-4 py-2 font-medium">الخطورة</th>
                    <th className="px-4 py-2 font-medium">التاريخ</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.cross_reference_findings.map((f) => {
                    const docId = findingDocId(f);
                    return (
                      <tr
                        key={f.id}
                        onClick={() => docId && void navigate({ to: "/owner/raw-data", search: { document_id: docId } })}
                        className={docId ? "cursor-pointer border-b border-border/50 last:border-0 hover:bg-accent/40" : "border-b border-border/50 last:border-0"}
                      >
                        <td className="px-4 py-2 text-muted-foreground">{f.finding_type}</td>
                        <td className="px-4 py-2 text-foreground">{f.description}</td>
                        <td className="px-4 py-2 text-red-600">
                          {f.variance_amount != null ? formatIQD(f.variance_amount) : f.variance_pct != null ? `${f.variance_pct}%` : "—"}
                        </td>
                        <td className={`px-4 py-2 ${SEV_COLOR[f.severity] ?? ""}`}>{SEV_LABELS[f.severity] ?? f.severity}</td>
                        <td className="px-4 py-2 text-muted-foreground" dir="ltr">{formatDate(f.created_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </section>

          {/* Anomalies */}
          <section className="overflow-hidden rounded-xl border border-border bg-card">
            <h2 className="border-b border-border px-4 py-3 text-sm font-semibold text-foreground">الشذوذ الرياضي</h2>
            {(data?.anomalies ?? []).length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-muted-foreground">لا يوجد شذوذ</p>
            ) : (
              <table className="w-full text-right text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-muted-foreground">
                    <th className="px-4 py-2 font-medium">العنوان</th>
                    <th className="px-4 py-2 font-medium">الوصف</th>
                    <th className="px-4 py-2 font-medium">الأثر المالي</th>
                    <th className="px-4 py-2 font-medium">الخطورة</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.anomalies.map((a) => (
                    <tr key={a.id} className="border-b border-border/50 last:border-0">
                      <td className="px-4 py-2 text-foreground">{a.title}</td>
                      <td className="px-4 py-2 text-muted-foreground">{a.description}</td>
                      <td className="px-4 py-2 text-red-600">{a.financial_impact != null ? formatIQD(a.financial_impact) : "—"}</td>
                      <td className={`px-4 py-2 ${SEV_COLOR[a.severity] ?? ""}`}>{SEV_LABELS[a.severity] ?? a.severity}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </div>
      )}
    </OwnerShell>
  );
}
