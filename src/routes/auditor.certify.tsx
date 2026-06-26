import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { RequireRole } from "@/components/RequireRole";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import {
  api,
  type CertificationDoc,
  type ExtractedFields,
  type FieldFlag,
} from "@/lib/api";

export const Route = createFileRoute("/auditor/certify")({
  head: () => ({ meta: [{ title: "اعتماد المستندات — AuditCore" }] }),
  component: () => (
    <RequireRole allow={["auditor", "admin", "appowner"]}>
      <CertifyPage />
    </RequireRole>
  ),
});

type FieldKey = keyof ExtractedFields;

const FIELD_LABELS: Record<FieldKey, string> = {
  invoice_number: "رقم الفاتورة",
  date: "التاريخ",
  amount: "المبلغ",
  vendor_name: "اسم المورد",
  items_list: "البنود",
};

const TEXT_FIELDS: FieldKey[] = ["invoice_number", "date", "amount", "vendor_name"];

const FLAG_STYLES: Record<FieldFlag, string> = {
  green: "border-green-500/50 bg-green-500/10",
  yellow: "border-yellow-500/60 bg-yellow-500/10",
  red: "border-destructive/60 bg-destructive/10",
};

function FlagIcon({ flag }: { flag: FieldFlag }) {
  if (flag === "green") return <span className="text-green-600">✓</span>;
  if (flag === "yellow") return <span className="text-yellow-600" title="تأكد من الحقل">⚠</span>;
  return <span className="text-destructive" title="حقل مطلوب">✕</span>;
}

function CertifyPage() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();

  const [doc, setDoc] = useState<CertificationDoc | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!loading && !user) void navigate({ to: "/login" });
  }, [user, loading, navigate]);

  const loadNext = useCallback(async () => {
    setError(null);
    setInfo(null);
    setBusy(true);
    try {
      const d = await api.nextCertification();
      setDoc(d);
      const f = d.extracted_data?.fields;
      setValues({
        invoice_number: f?.invoice_number ?? "",
        date: f?.date ?? "",
        amount: f?.amount ?? "",
        vendor_name: f?.vendor_name ?? "",
      });
      setDone(false);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "خطأ";
      // 404 -> no pending documents (assembly line empty)
      setDoc(null);
      setDone(true);
      setInfo(msg);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (user) void loadNext();
  }, [user, loadNext]);

  const flags = doc?.extracted_data?.color_flags;

  const redUnfilled = useMemo(() => {
    if (!flags) return [];
    return TEXT_FIELDS.filter(
      (k) => flags[k] === "red" && !(values[k] && values[k].trim()),
    );
  }, [flags, values]);

  const canCertify = doc !== null && redUnfilled.length === 0 && !busy;

  async function onCertify() {
    if (!doc) return;
    setBusy(true);
    setError(null);
    try {
      const corrected: Record<string, unknown> = {
        invoice_number: values.invoice_number || null,
        date: values.date || null,
        amount: values.amount || null,
        vendor_name: values.vendor_name || null,
      };
      const res = await api.certify(doc.document_id, corrected, true);
      setInfo(`تم الاعتماد ✓ (سلسلة التدقيق: ${res.ledger_hash.slice(0, 12)}…)`);
      // Assembly line: auto-load the next document.
      await loadNext();
    } catch (e) {
      setError(e instanceof Error ? e.message : "فشل الاعتماد");
      setBusy(false);
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
    <div className="min-h-screen bg-background px-4 py-6" dir="rtl">
      <div className="mx-auto max-w-6xl">
        <header className="flex items-center justify-between border-b border-border pb-4">
          <div>
            <h1 className="text-2xl font-bold text-foreground">اعتماد المستندات</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              راجع البيانات المستخرجة وصحّح الحقول ثم اعتمد المستند
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

        {info && (
          <div className="mt-4 rounded-md border border-green-500/40 bg-green-500/10 px-4 py-3 text-right text-sm text-green-700 dark:text-green-400">
            {info}
          </div>
        )}
        {error && (
          <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-right text-sm text-destructive">
            {error}
          </div>
        )}

        {done && !doc ? (
          <div className="mt-10 rounded-xl border border-border bg-card p-10 text-center">
            <p className="text-lg font-medium text-foreground">لا توجد مستندات بانتظار الاعتماد 🎉</p>
            <button
              onClick={() => void loadNext()}
              className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              تحديث
            </button>
          </div>
        ) : (
          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* LEFT (in RTL appears first / right side visually): form fields */}
            <section className="order-2 rounded-xl border border-border bg-card p-5 lg:order-1">
              <h2 className="mb-1 text-sm font-semibold text-foreground">البيانات المستخرجة</h2>
              {doc && (
                <p className="mb-4 text-xs text-muted-foreground">
                  {doc.original_filename} — درجة الثقة:{" "}
                  {doc.confidence_score != null ? `${doc.confidence_score}%` : "—"}
                </p>
              )}

              {TEXT_FIELDS.map((key) => {
                const flag = flags?.[key] ?? "red";
                return (
                  <div key={key} className="mb-4">
                    <label className="mb-1 flex items-center justify-end gap-2 text-sm font-medium text-foreground">
                      {flag === "red" && <span className="text-xs text-destructive">(مطلوب)</span>}
                      <FlagIcon flag={flag} />
                      {FIELD_LABELS[key]}
                    </label>
                    <input
                      type="text"
                      dir={key === "amount" || key === "invoice_number" || key === "date" ? "ltr" : "rtl"}
                      value={values[key] ?? ""}
                      onChange={(e) =>
                        setValues((v) => ({ ...v, [key]: e.target.value }))
                      }
                      className={[
                        "w-full rounded-md border px-3 py-2 text-right text-sm outline-none focus:ring-2 focus:ring-primary/40",
                        FLAG_STYLES[flag],
                      ].join(" ")}
                      placeholder={flag === "red" ? "الرجاء إدخال القيمة" : ""}
                    />
                  </div>
                );
              })}

              {/* items list (read-only summary) */}
              <div className="mb-4">
                <label className="mb-1 flex items-center justify-end gap-2 text-sm font-medium text-foreground">
                  <FlagIcon flag={flags?.items_list ?? "red"} />
                  {FIELD_LABELS.items_list}
                </label>
                <div
                  className={[
                    "max-h-40 overflow-y-auto rounded-md border px-3 py-2 text-right text-sm",
                    FLAG_STYLES[flags?.items_list ?? "red"],
                  ].join(" ")}
                >
                  {doc?.extracted_data?.fields.items_list?.length ? (
                    <ul className="space-y-1">
                      {doc.extracted_data.fields.items_list.map((it, i) => (
                        <li key={i} className="flex justify-between gap-2">
                          <span className="text-muted-foreground" dir="ltr">{it.value}</span>
                          <span className="text-foreground">{it.description}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="text-muted-foreground">لا توجد بنود مستخرجة</span>
                  )}
                </div>
              </div>

              {redUnfilled.length > 0 && (
                <p className="mb-3 text-xs text-destructive">
                  يجب تعبئة الحقول المطلوبة (الحمراء) قبل الاعتماد.
                </p>
              )}

              <button
                onClick={() => void onCertify()}
                disabled={!canCertify}
                className="w-full rounded-md bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy ? "جارٍ المعالجة..." : "تأكيد واعتماد المستند"}
              </button>
            </section>

            {/* RIGHT (visually right in RTL): original image */}
            <section className="order-1 rounded-xl border border-border bg-muted/30 p-3 lg:order-2">
              <h2 className="mb-2 px-2 text-sm font-semibold text-foreground">المستند الأصلي</h2>
              <div className="flex min-h-[400px] items-center justify-center overflow-auto rounded-lg bg-white p-2">
                {busy && !doc ? (
                  <p className="text-muted-foreground">جارٍ التحميل...</p>
                ) : doc?.original_image_url ? (
                  doc.file_type === "pdf" ? (
                    <iframe
                      title="المستند"
                      src={doc.original_image_url}
                      className="h-[600px] w-full"
                    />
                  ) : (
                    <img
                      src={doc.original_image_url}
                      alt="المستند الأصلي"
                      className="max-h-[600px] max-w-full object-contain"
                    />
                  )
                ) : (
                  <p className="text-muted-foreground">لا تتوفر معاينة للمستند</p>
                )}
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
