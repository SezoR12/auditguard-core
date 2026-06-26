import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { OwnerShell } from "@/components/OwnerShell";
import { api, type DashLayer4 } from "@/lib/api";
import { formatDate } from "@/lib/format";

interface Search {
  document_id?: string;
}

export const Route = createFileRoute("/owner/raw-data")({
  validateSearch: (s: Record<string, unknown>): Search => ({
    document_id: typeof s.document_id === "string" ? s.document_id : undefined,
  }),
  head: () => ({ meta: [{ title: "السجل الأصلي — AuditCore" }] }),
  component: OwnerLayer4,
});

function OwnerLayer4() {
  const search = Route.useSearch();
  const [docId, setDocId] = useState(search.document_id ?? "");
  const [data, setData] = useState<DashLayer4 | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (id: string) => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      setData(await api.dashLayer4(id));
    } catch (e) {
      setData(null);
      setError(e instanceof Error ? e.message : "تعذّر تحميل المستند");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (search.document_id) void load(search.document_id);
  }, [search.document_id, load]);

  return (
    <OwnerShell title="السجل الأصلي" subtitle="هذا هو السجل الأصلي — شفافية كاملة">
      {/* Manual lookup */}
      <div className="mb-6 flex items-end gap-2">
        <div className="flex-1">
          <label className="mb-1 block text-xs text-muted-foreground">معرّف المستند</label>
          <input
            value={docId}
            onChange={(e) => setDocId(e.target.value)}
            placeholder="document_id (UUID)"
            dir="ltr"
            className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm"
          />
        </div>
        <button onClick={() => void load(docId)} className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90">
          عرض
        </button>
      </div>

      {loading ? (
        <p className="py-16 text-center text-muted-foreground">جاري تحليل البيانات...</p>
      ) : error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-right text-sm text-destructive">{error}</div>
      ) : !data ? (
        <p className="py-16 text-center text-muted-foreground">أدخل معرّف مستند لعرض سجله الأصلي.</p>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Original image */}
          <section className="rounded-xl border border-border bg-muted/30 p-3">
            <h2 className="mb-2 px-1 text-sm font-semibold text-foreground">المستند الأصلي</h2>
            <div className="flex min-h-[360px] items-center justify-center overflow-auto rounded-lg bg-white p-2">
              {data.original_image_url ? (
                data.file_type === "pdf" ? (
                  <iframe title="doc" src={data.original_image_url} className="h-[560px] w-full" />
                ) : (
                  <img src={data.original_image_url} alt="المستند" className="max-h-[560px] max-w-full object-contain" />
                )
              ) : (
                <p className="text-muted-foreground">لا تتوفر معاينة</p>
              )}
            </div>
          </section>

          {/* Details */}
          <section className="space-y-4">
            <div className="rounded-xl border border-border bg-card p-4 text-right">
              <h2 className="mb-2 text-sm font-semibold text-foreground">البيانات المعتمدة</h2>
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between"><dt className="text-muted-foreground">الملف</dt><dd>{data.original_filename}</dd></div>
                <div className="flex justify-between"><dt className="text-muted-foreground">الحالة</dt><dd>{data.status}</dd></div>
                <div className="flex justify-between"><dt className="text-muted-foreground">درجة الثقة</dt><dd>{data.confidence_score ?? "—"}</dd></div>
                <div className="flex justify-between"><dt className="text-muted-foreground">رفع بواسطة</dt><dd>{data.uploaded_by_name ?? "—"}</dd></div>
              </dl>
              {data.extracted_data && typeof data.extracted_data === "object" && "fields" in data.extracted_data && (
                <div className="mt-3 rounded-md bg-muted/40 p-2 text-xs">
                  <pre className="overflow-x-auto whitespace-pre-wrap" dir="ltr">
                    {JSON.stringify((data.extracted_data as { fields: unknown }).fields, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            {/* Certifications */}
            <div className="rounded-xl border border-border bg-card p-4">
              <h2 className="mb-2 text-sm font-semibold text-foreground">سجل الاعتماد</h2>
              {data.certifications.length === 0 ? (
                <p className="text-sm text-muted-foreground">لا توجد اعتمادات</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {data.certifications.map((c) => (
                    <li key={c.id} className="rounded-md border border-border/60 p-2">
                      <div className="flex justify-between">
                        <span className={c.is_valid ? "text-green-600" : "text-red-600"}>{c.is_valid ? "✓ صالح" : "✗ غير صالح"}</span>
                        <span className="text-foreground">{c.auditor_name ?? "—"}</span>
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground" dir="ltr">{formatDate(c.certified_at)}</div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Ledger */}
            <div className="rounded-xl border border-border bg-card p-4">
              <h2 className="mb-2 text-sm font-semibold text-foreground">سجل التدقيق المرتبط</h2>
              {data.ledger_entries.length === 0 ? (
                <p className="text-sm text-muted-foreground">لا توجد قيود</p>
              ) : (
                <ul className="space-y-2 text-xs">
                  {data.ledger_entries.map((l) => (
                    <li key={l.id} className="rounded-md border border-border/60 p-2">
                      <div className="flex justify-between">
                        <span className="font-medium text-foreground">{l.action}</span>
                        <span className="text-muted-foreground">{l.created_by_name ?? "النظام"}</span>
                      </div>
                      {l.reason && <div className="mt-1 text-muted-foreground">{l.reason}</div>}
                      <div className="mt-1 font-mono text-[10px] text-muted-foreground" dir="ltr">{l.current_hash.slice(0, 20)}…</div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        </div>
      )}
    </OwnerShell>
  );
}
