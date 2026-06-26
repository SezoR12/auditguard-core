import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { useAuth } from "@/hooks/useAuth";
import { api, type DocumentItem } from "@/lib/api";

export const Route = createFileRoute("/auditor/upload")({
  head: () => ({ meta: [{ title: "رفع المستندات — AuditCore" }] }),
  component: UploadPage,
});

// Arabic category labels mapped to backend category keys.
const CATEGORIES: { key: string; label: string }[] = [
  { key: "invoice", label: "فاتورة" },
  { key: "bank_statement", label: "كشف حساب بنكي" },
  { key: "contract", label: "عقد" },
  { key: "inventory_report", label: "تقرير جرد" },
  { key: "encrypted_accounting", label: "تقرير محاسبي مشفر" },
  { key: "receipt", label: "إيصال" },
  { key: "report", label: "تقرير" },
  { key: "other", label: "أخرى" },
];

const STATUS_LABELS: Record<DocumentItem["status"], string> = {
  pending: "قيد الانتظار",
  ocr_processing: "قيد المعالجة",
  certified: "موثّق",
};

const CATEGORY_LABELS: Record<DocumentItem["doc_category"], string> = {
  invoice: "فاتورة",
  receipt: "إيصال",
  contract: "عقد",
  report: "تقرير",
  statement: "كشف حساب",
  other: "أخرى",
};

const ACCEPT = {
  "application/pdf": [".pdf"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/png": [".png"],
  "image/tiff": [".tiff", ".tif"],
  "text/csv": [".csv"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
  "application/json": [".json"],
};

const MAX_SIZE = 50 * 1024 * 1024;

function formatDate(iso: string): string {
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

function UploadPage() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();

  const [category, setCategory] = useState<string>("invoice");
  const [progress, setProgress] = useState<number | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);

  useEffect(() => {
    if (!loading && !user) void navigate({ to: "/login" });
  }, [user, loading, navigate]);

  const reloadDocs = useCallback(async () => {
    setLoadingDocs(true);
    try {
      setDocs(await api.myUploads());
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر تحميل المستندات");
    } finally {
      setLoadingDocs(false);
    }
  }, []);

  useEffect(() => {
    if (user) void reloadDocs();
  }, [user, reloadDocs]);

  const onDrop = useCallback(
    async (accepted: File[], rejections: FileRejection[]) => {
      setError(null);
      setSuccess(null);

      if (rejections.length > 0) {
        const r = rejections[0];
        const code = r.errors[0]?.code;
        if (code === "file-too-large") setError("حجم الملف يتجاوز 50 ميغابايت");
        else if (code === "file-invalid-type") setError("نوع الملف غير مدعوم");
        else setError(r.errors[0]?.message ?? "تم رفض الملف");
        return;
      }
      if (accepted.length === 0) return;

      const file = accepted[0];
      setProgress(0);
      try {
        const res = await api.uploadDocument(
          file,
          category,
          user?.branch_id ?? null,
          (pct) => setProgress(pct),
        );
        setSuccess(`تم الرفع بنجاح: ${res.original_filename}`);
        setProgress(null);
        await reloadDocs();
      } catch (e) {
        setProgress(null);
        setError(e instanceof Error ? e.message : "فشل الرفع");
      }
    },
    [category, user, reloadDocs],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPT,
    maxSize: MAX_SIZE,
    multiple: false,
    disabled: progress !== null,
  });

  const dropzoneClasses = useMemo(
    () =>
      [
        "flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 text-center transition cursor-pointer",
        isDragActive
          ? "border-primary bg-primary/5"
          : "border-input bg-muted/30 hover:bg-muted/50",
        progress !== null ? "pointer-events-none opacity-60" : "",
      ].join(" "),
    [isDragActive, progress],
  );

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-muted-foreground">جارٍ التحميل...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background px-6 py-10" dir="rtl">
      <div className="mx-auto max-w-4xl">
        <header className="flex items-center justify-between border-b border-border pb-4">
          <div>
            <h1 className="text-2xl font-bold text-foreground">رفع المستندات</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              مرحباً {user.full_name} — قم برفع المستندات لتدقيقها
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

        <main className="mt-8 space-y-6">
          {/* Category select */}
          <div className="text-right">
            <label className="mb-1 block text-sm font-medium text-foreground">
              نوع المستند
            </label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full max-w-xs rounded-md border border-input bg-background px-3 py-2 text-right text-sm"
            >
              {CATEGORIES.map((c) => (
                <option key={c.key} value={c.key}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          {/* Dropzone */}
          <div {...getRootProps()} className={dropzoneClasses}>
            <input {...getInputProps()} />
            <svg
              className="mb-3 h-10 w-10 text-muted-foreground"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 7.5 7.5 12M12 7.5V21"
              />
            </svg>
            {isDragActive ? (
              <p className="text-sm font-medium text-primary">أفلت الملف هنا...</p>
            ) : (
              <>
                <p className="text-sm font-medium text-foreground">
                  اسحب الملف وأفلته هنا، أو انقر للاختيار
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  المسموح: xlsx, csv, docx, jpg, jpeg, png, tiff, pdf, json — بحد أقصى 50 ميغابايت
                </p>
              </>
            )}
          </div>

          {/* Progress */}
          {progress !== null && (
            <div>
              <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                <span>جارٍ الرفع...</span>
                <span>{progress}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full bg-primary transition-all"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {/* Alerts */}
          {success && (
            <div className="rounded-md border border-green-500/40 bg-green-500/10 px-4 py-3 text-right text-sm text-green-700 dark:text-green-400">
              {success}
            </div>
          )}
          {error && (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-right text-sm text-destructive">
              {error}
            </div>
          )}

          {/* Uploaded documents table */}
          <section className="rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 className="text-sm font-semibold text-foreground">مستنداتي المرفوعة</h2>
              <button
                onClick={() => void reloadDocs()}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                تحديث
              </button>
            </div>
            {loadingDocs ? (
              <p className="px-4 py-6 text-center text-sm text-muted-foreground">جارٍ التحميل...</p>
            ) : docs.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-muted-foreground">
                لا توجد مستندات بعد
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-right text-sm">
                  <thead>
                    <tr className="border-b border-border text-xs text-muted-foreground">
                      <th className="px-4 py-2 font-medium">اسم الملف</th>
                      <th className="px-4 py-2 font-medium">التصنيف</th>
                      <th className="px-4 py-2 font-medium">الحالة</th>
                      <th className="px-4 py-2 font-medium">تاريخ الرفع</th>
                    </tr>
                  </thead>
                  <tbody>
                    {docs.map((d) => (
                      <tr key={d.id} className="border-b border-border/50 last:border-0">
                        <td className="px-4 py-2 text-foreground">{d.original_filename}</td>
                        <td className="px-4 py-2 text-muted-foreground">
                          {CATEGORY_LABELS[d.doc_category]}
                        </td>
                        <td className="px-4 py-2">
                          <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-foreground">
                            {STATUS_LABELS[d.status]}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-muted-foreground">{formatDate(d.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </main>
      </div>
    </div>
  );
}
