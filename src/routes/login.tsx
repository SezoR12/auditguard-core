import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useAuth, roleHomePath } from "@/hooks/useAuth";
import { API_URL } from "@/lib/api";
import { getPreviewAuthStatus, PREVIEW_BACKEND_HELP } from "@/lib/authPreview";

export const Route = createFileRoute("/login")({
  head: () => ({ meta: [{ title: "تسجيل الدخول — AuditCore" }] }),
  component: LoginPage,
});

function LoginPage() {
  const { user, loading, login, authHint, clearAuthHint } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [previewWarning, setPreviewWarning] = useState<string | null>(null);
  const [seedGuidance, setSeedGuidance] = useState<string | null>(null);
  const [seededEmails, setSeededEmails] = useState<string[]>([]);

  useEffect(() => {
    if (!loading && user) {
      void navigate({ to: roleHomePath(user.role) });
    }
  }, [user, loading, navigate]);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const status = await getPreviewAuthStatus(API_URL);
        if (cancelled) return;

        if (!status.backendReachable) {
          setPreviewWarning(PREVIEW_BACKEND_HELP);
        } else {
          setPreviewWarning(null);
        }

        setSeededEmails(status.availableSeedEmails);
        if (!status.seededUsersFound) {
          setSeedGuidance(
            "لم يتم العثور على المستخدمين التجريبيين في Supabase. شغّل ./setup.sh أو python backend/scripts/seed.py بعد ضبط SUPABASE_URL و SUPABASE_SERVICE_ROLE_KEY.",
          );
        } else {
          setSeedGuidance(null);
        }
      } catch {
        if (cancelled) return;
        setPreviewWarning(
          "بيئة Lovable لا تستطيع الوصول إلى FastAPI أو Supabase بالإعدادات الحالية. تحقّق من VITE_AUDITCORE_SUPABASE_URL و VITE_AUDITCORE_SUPABASE_ANON_KEY، أو شغّل الخلفية محليًا.",
        );
        setSeedGuidance(
          "إذا كنت تعمل من Lovable فقط، تأكد من حقن متغيرات Supabase الصحيحة. وإذا كنت تعمل محليًا، شغّل ./preview-backend.sh أو ./setup.sh ثم أعد المحاولة.",
        );
        setSeededEmails([]);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    clearAuthHint();
    setSubmitting(true);
    try {
      const me = await login(email, password);
      void navigate({ to: roleHomePath(me.role) });
    } catch (err) {
      setError(err instanceof Error ? err.message : "فشل تسجيل الدخول");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4" dir="rtl">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card p-8 shadow-sm">
        <h1 className="text-2xl font-bold text-foreground">AuditCore</h1>
        <p className="mt-1 text-sm text-muted-foreground">منصة التدقيق الداخلي</p>

        <form onSubmit={onSubmit} className="mt-6 space-y-4 text-right">
          {previewWarning && (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-3 text-sm text-amber-900 dark:text-amber-200">
              <div className="font-medium">تنبيه وضع المعاينة</div>
              <div className="mt-1">{previewWarning}</div>
              <div className="mt-2 text-xs opacity-80">
                اقتراح: شغّل <code>./preview-backend.sh</code> أو <code>./setup.sh</code> لتفعيل FastAPI محليًا، أو استمر في وضع Supabase فقط.
              </div>
            </div>
          )}

          {seedGuidance && (
            <div className="rounded-md border border-blue-500/40 bg-blue-500/10 px-3 py-3 text-sm text-blue-900 dark:text-blue-200">
              <div className="font-medium">إرشادات التهيئة الأولية</div>
              <div className="mt-1">{seedGuidance}</div>
              <div className="mt-2 text-xs opacity-80">
                بعد تشغيل seed ستظهر الحسابات التجريبية الجاهزة لتسجيل الدخول.
              </div>
            </div>
          )}

          {!seedGuidance && seededEmails.length > 0 && (
            <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-3 text-emerald-900 dark:text-emerald-200">
              <div className="font-medium text-sm">الحسابات التجريبية الجاهزة</div>
              <div className="mt-1 text-xs opacity-80">
                تم العثور على مستخدمين تجريبيين في Supabase. يمكنك استخدام أحد الحسابات التالية:
              </div>
              <div className="mt-3 space-y-2 text-xs">
                {[
                  { role: "المالك", email: "owner@auditcore.local", password: "Owner123!" },
                  { role: "المدير العام", email: "gm@auditcore.local", password: "Gm123!" },
                  { role: "مدير الفرع", email: "manager@auditcore.local", password: "Manager123!" },
                  { role: "المدقق", email: "auditor@auditcore.local", password: "Auditor123!" },
                ]
                  .filter((account) => seededEmails.includes(account.email))
                  .map((account) => (
                    <div key={account.email} className="rounded-md border border-emerald-500/20 bg-white/50 px-3 py-2 dark:bg-black/10">
                      <div className="font-medium">{account.role}</div>
                      <div className="mt-1 font-mono break-all">{account.email}</div>
                      <div className="mt-1 font-mono">{account.password}</div>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {authHint && (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-900 dark:text-amber-200">
              {authHint}
            </div>
          )}
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium text-foreground">
              البريد الإلكتروني
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-right text-sm outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium text-foreground">
              كلمة المرور
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-right text-sm outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          {error && (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {submitting ? "..." : "تسجيل الدخول"}
          </button>
        </form>
      </div>
    </div>
  );
}
