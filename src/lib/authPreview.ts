import { supabaseAuditcore } from "@/lib/supabaseClient";
import type { CurrentUser } from "@/lib/api";

export interface PreviewAuthStatus {
  backendReachable: boolean;
  seededUsersFound: boolean;
  availableSeedEmails: string[];
}

export class PreviewBackendUnavailableError extends Error {
  constructor(message = "تعذّر الوصول إلى خدمة FastAPI في وضع المعاينة") {
    super(message);
    this.name = "PreviewBackendUnavailableError";
  }
}

const SEED_EMAILS = [
  "owner@auditcore.local",
  "gm@auditcore.local",
  "manager@auditcore.local",
  "auditor@auditcore.local",
] as const;

export const PREVIEW_BACKEND_HELP =
  "تعذّر الوصول إلى FastAPI عبر api.me() في وضع المعاينة. يمكنك تشغيل الخلفية محليًا عبر Docker/Compose أو الاعتماد على وضع Supabase فقط للمعاينة.";

export async function isFastApiReachable(apiUrl: string): Promise<boolean> {
  try {
    const res = await fetch(`${apiUrl}/health`, { method: "GET" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function getPreviewAuthStatus(apiUrl: string): Promise<PreviewAuthStatus> {
  const [backendReachable, availableSeedEmails] = await Promise.all([
    isFastApiReachable(apiUrl),
    findAvailableSeedUsers(),
  ]);

  return {
    backendReachable,
    seededUsersFound: availableSeedEmails.length > 0,
    availableSeedEmails,
  };
}

export async function findAvailableSeedUsers(): Promise<string[]> {
  const checks = await Promise.all(
    SEED_EMAILS.map(async (email) => {
      const { data, error } = await supabaseAuditcore
        .from("users")
        .select("email")
        .eq("email", email)
        .limit(1);

      if (error) return null;
      return data && data.length > 0 ? email : null;
    }),
  );

  return checks.filter((email): email is (typeof SEED_EMAILS)[number] => Boolean(email));
}

export async function loadProfileFromSupabase(): Promise<CurrentUser> {
  const { data: sessionData } = await supabaseAuditcore.auth.getSession();
  const session = sessionData.session;
  if (!session?.user) {
    throw new Error("لا توجد جلسة Supabase نشطة");
  }

  const authUserId = session.user.id;
  const email = session.user.email?.toLowerCase() ?? null;

  let query = supabaseAuditcore
    .from("users")
    .select("id, email, full_name, role, company_id, branch_id, is_active, auth_user_id")
    .limit(1);

  query = email ? query.or(`auth_user_id.eq.${authUserId},email.eq.${email}`) : query.eq("auth_user_id", authUserId);

  const { data, error } = await query.maybeSingle();

  if (error) {
    throw new Error("فشل جلب ملف المستخدم من Supabase");
  }

  if (!data) {
    throw new Error("لم يتم العثور على ملف المستخدم في جدول public.users. شغّل backend/scripts/seed.py أولاً.");
  }

  if (!data.is_active) {
    throw new Error("حساب المستخدم غير مفعّل في public.users");
  }

  return {
    id: String(data.id),
    email: data.email,
    full_name: data.full_name,
    role: data.role,
    company_id: String(data.company_id),
    branch_id: data.branch_id ? String(data.branch_id) : null,
    is_active: Boolean(data.is_active),
  } as CurrentUser;
}
