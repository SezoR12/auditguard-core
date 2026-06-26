import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { api, type LedgerEntry, type LedgerVerifyResult } from "@/lib/api";

export const Route = createFileRoute("/owner/ledger")({
  head: () => ({ meta: [{ title: "سجل التدقيق — AuditCore" }] }),
  component: LedgerPage,
});

const TABLE_LABELS: Record<string, string> = {
  documents: "المستندات",
  document_certifications: "اعتمادات المستندات",
  audit_tasks: "المهام",
};

const ACTION_LABELS: Record<string, string> = {
  insert: "إضافة",
  update: "تحديث",
  delete: "حذف",
  reverse: "عكس",
};

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ar-IQ", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function LedgerPage() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();

  const [entries, setEntries] = useState<LedgerEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingRows, setLoadingRows] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<LedgerVerifyResult | null>(null);

  // Filters
  const [tableFilter, setTableFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  useEffect(() => {
    if (!loading && !user) void navigate({ to: "/login" });
  }, [user, loading, navigate]);

  const reload = useCallback(async () => {
    setLoadingRows(true);
    setError(null);
    try {
      const page = await api.ledger({
        limit: 100,
        table_name: tableFilter || undefined,
        date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
        date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
      });
      setEntries(page.entries);
      setTotal(page.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر تحميل السجل");
    } finally {
      setLoadingRows(false);
    }
  }, [tableFilter, dateFrom, dateTo]);

  useEffect(() => {
    if (user) void reload();
  }, [user, reload]);

  async function onVerify() {
    setVerifying(true);
    setVerifyResult(null);
    setError(null);
    try {
      setVerifyResult(await api.verifyLedger());
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر التحقق من السلسلة");
    } finally {
      setVerifying(false);
    }
  }

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-muted-foreground">جارٍ التحميل...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background px-6 py-8" dir="rtl">
      <div className="mx-auto max-w-6xl">
        <header className="flex items-center justify-between border-b border-border pb-4">
          <div>
            <h1 className="text-2xl font-bold text-foreground">سجل التدقيق المُحصَّن</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              سلسلة مشفّرة لكل العمليات — يمكنك إثبات عدم التلاعب بالتاريخ
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

        {/* Verify banner */}
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <button
            onClick={() => void onVerify()}
            disabled={verifying}
            className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-60"
          >
            {verifying ? "جارٍ التحقق..." : "التحقق من سلامة السلسلة"}
          </button>

          {verifyResult && verifyResult.is_valid && (
            <div className="rounded-md border border-green-500/40 bg-green-500/10 px-4 py-2 text-sm font-medium text-green-700 dark:text-green-400">
              ✓ السجل سليم 100% — {verifyResult.total_entries} عملية، السلسلة متصلة بالكامل
            </div>
          )}
          {verifyResult && !verifyResult.is_valid && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-2 text-sm font-medium text-destructive">
              ✕ تم اكتشاف تلاعب! روابط مكسورة: {verifyResult.broken_links.length} (
              {verifyResult.broken_links.map((b) => b.slice(0, 8)).join("، ")})
            </div>
          )}
        </div>

        {/* Filters */}
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">الجدول</label>
            <select
              value={tableFilter}
              onChange={(e) => setTableFilter(e.target.value)}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-right text-sm"
            >
              <option value="">الكل</option>
              <option value="documents">المستندات</option>
              <option value="document_certifications">اعتمادات المستندات</option>
              <option value="audit_tasks">المهام</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">من تاريخ</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">إلى تاريخ</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
            />
          </div>
          <button
            onClick={() => void reload()}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
          >
            تطبيق
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-right text-sm text-destructive">
            {error}
          </div>
        )}

        {/* Ledger table */}
        <section className="mt-6 overflow-hidden rounded-xl border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold text-foreground">
              العمليات ({total})
            </h2>
            <button
              onClick={() => void reload()}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              تحديث
            </button>
          </div>

          {loadingRows ? (
            <p className="px-4 py-8 text-center text-sm text-muted-foreground">جارٍ التحميل...</p>
          ) : entries.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-muted-foreground">لا توجد عمليات</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-right text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-muted-foreground">
                    <th className="px-4 py-2 font-medium">التاريخ</th>
                    <th className="px-4 py-2 font-medium">المستخدم</th>
                    <th className="px-4 py-2 font-medium">الجدول</th>
                    <th className="px-4 py-2 font-medium">العملية</th>
                    <th className="px-4 py-2 font-medium">السبب</th>
                    <th className="px-4 py-2 font-medium">رمز التحقق</th>
                    <th className="px-4 py-2 font-medium">الحالة</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e) => (
                    <tr key={e.id} className="border-b border-border/50 last:border-0">
                      <td className="px-4 py-2 text-muted-foreground" dir="ltr">
                        {fmtDate(e.created_at)}
                      </td>
                      <td className="px-4 py-2 text-foreground">
                        {e.created_by_name ?? (e.created_by ? e.created_by.slice(0, 8) : "النظام")}
                      </td>
                      <td className="px-4 py-2 text-muted-foreground">
                        {TABLE_LABELS[e.table_name] ?? e.table_name}
                      </td>
                      <td className="px-4 py-2 text-muted-foreground">
                        {ACTION_LABELS[e.action] ?? e.action}
                      </td>
                      <td className="px-4 py-2 text-muted-foreground" title={e.reason ?? ""}>
                        <span className="line-clamp-1 max-w-[260px]">{e.reason ?? "—"}</span>
                      </td>
                      <td className="px-4 py-2 font-mono text-xs text-muted-foreground" dir="ltr" title={e.current_hash}>
                        {e.current_hash.slice(0, 12)}…
                      </td>
                      <td className="px-4 py-2">
                        {e.chain_status === "valid" ? (
                          <span className="rounded-full bg-green-500/10 px-2 py-0.5 text-xs text-green-700 dark:text-green-400">
                            سليم
                          </span>
                        ) : (
                          <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-xs text-destructive">
                            تلاعب
                          </span>
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
