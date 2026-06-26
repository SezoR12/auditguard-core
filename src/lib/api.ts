// Thin fetch wrapper for the FastAPI backend.
// Auth: bearer token comes from the Supabase session, not a local-only JWT.
import { supabaseAuditcore } from "@/lib/supabaseClient";

const API_URL =
  (import.meta.env.VITE_AUDITCORE_API_URL as string | undefined) ?? "http://localhost:8000";

async function getAccessToken(): Promise<string | null> {
  const { data } = await supabaseAuditcore.auth.getSession();
  return data.session?.access_token ?? null;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = await getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string;
  role: "owner" | "gm" | "manager" | "auditor" | "admin" | "appowner";
  company_id: string;
  branch_id: string | null;
  is_active: boolean;
}

export interface DocumentItem {
  id: string;
  original_filename: string;
  file_type: "excel" | "csv" | "word" | "image" | "pdf" | "encrypted_json";
  doc_category: "invoice" | "receipt" | "contract" | "report" | "statement" | "other";
  status: "pending" | "ocr_processing" | "certified";
  uploaded_by: string;
  company_id: string;
  branch_id: string | null;
  ocr_status: string | null;
  confidence_score: number | null;
  created_at: string;
}

export interface UploadResult {
  document_id: string;
  status: DocumentItem["status"];
  file_type: DocumentItem["file_type"];
  doc_category: DocumentItem["doc_category"];
  original_filename: string;
  message: string;
}

/** Multipart upload via XHR so we can report progress. */
export async function uploadDocument(
  file: File,
  docCategory: string,
  branchId: string | null,
  onProgress?: (pct: number) => void,
): Promise<UploadResult> {
  const token = await getAccessToken();
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    form.append("doc_category", docCategory);
    if (branchId) form.append("branch_id", branchId);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/documents/upload`);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as UploadResult);
      } else {
        let detail = `HTTP ${xhr.status}`;
        try {
          const body = JSON.parse(xhr.responseText);
          if (body?.detail) detail = body.detail;
        } catch {
          /* ignore */
        }
        reject(new Error(detail));
      }
    };
    xhr.onerror = () => reject(new Error("تعذّر الاتصال بالخادم"));
    xhr.send(form);
  });
}

export type FieldFlag = "green" | "yellow" | "red";

export interface ExtractedFields {
  invoice_number: string | null;
  date: string | null;
  amount: string | null;
  vendor_name: string | null;
  items_list: Array<{ description: string; value: string }>;
}

export interface ExtractedData {
  fields: ExtractedFields;
  confidences: Record<string, number | null>;
  color_flags: Record<keyof ExtractedFields, FieldFlag>;
  overall_confidence: number | null;
  raw_text?: string;
}

export interface CertificationDoc {
  document_id: string;
  original_filename: string;
  file_type: string;
  doc_category: string;
  confidence_score: number | null;
  original_image_url: string | null;
  extracted_data: ExtractedData | null;
}

export interface CertifyResult {
  document_id: string;
  certification_id: string;
  status: string;
  ledger_hash: string;
  message: string;
}

export type TaskColor = "green" | "yellow" | "red";

export interface TaskItem {
  id: string;
  title: string;
  task_type: string;
  status: "pending" | "in_progress" | "completed" | "overdue";
  is_critical: boolean;
  sla_deadline: string | null;
  completed_at: string | null;
  demerit_points: number;
  created_at: string;
  time_remaining_seconds: number | null;
  time_color: TaskColor;
}

export interface TaskCompleteResult {
  task_id: string;
  status: string;
  completed_at: string;
  on_time: boolean;
  message: string;
}

export interface AuditorPerformanceRow {
  auditor_id: string;
  full_name: string;
  tasks_completed_today: number;
  tasks_delayed: number;
  demerit_points: number;
  efficiency_score: number;
}

export const api = {
  me: () => request<CurrentUser>("/auth/me"),

  myUploads: () => request<DocumentItem[]>("/documents/my-uploads"),
  pendingCertification: () => request<DocumentItem[]>("/documents/pending-certification"),
  companyDocuments: () => request<DocumentItem[]>("/documents/company"),
  uploadDocument,

  nextCertification: () => request<CertificationDoc>("/certification/next"),
  certify: (docId: string, correctedFields: Record<string, unknown>, isValid: boolean) =>
    request<CertifyResult>(`/certification/${docId}/certify`, {
      method: "POST",
      body: JSON.stringify({ corrected_fields: correctedFields, is_valid: isValid }),
    }),

  myTasks: () => request<TaskItem[]>("/tasks/my-tasks"),
  completeTask: (taskId: string) =>
    request<TaskCompleteResult>(`/tasks/${taskId}/complete`, { method: "POST" }),
  auditorPerformance: () => request<AuditorPerformanceRow[]>("/owner/auditor-performance"),

  dashLayer1: () => request<DashLayer1>("/owner/dashboard/layer1"),
  dashLayer2: () => request<DashLayer2>("/owner/dashboard/layer2"),
  dashLayer3: (params: { department?: string; severity?: string; date_from?: string; date_to?: string } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v) q.set(k, String(v));
    });
    const qs = q.toString();
    return request<DashLayer3>(`/owner/dashboard/layer3${qs ? `?${qs}` : ""}`);
  },
  dashLayer4: (documentId: string) => request<DashLayer4>(`/owner/dashboard/layer4/${documentId}`),

  ledger: (params: {
    limit?: number;
    offset?: number;
    table_name?: string;
    user_id?: string;
    date_from?: string;
    date_to?: string;
  } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
    });
    const qs = q.toString();
    return request<LedgerPage>(`/owner/ledger${qs ? `?${qs}` : ""}`);
  },
  verifyLedger: () => request<LedgerVerifyResult>("/owner/ledger/verify"),
};

export interface LedgerEntry {
  id: string;
  created_at: string;
  created_by: string | null;
  created_by_name: string | null;
  table_name: string;
  record_id: string;
  action: string;
  reason: string | null;
  previous_hash: string | null;
  current_hash: string;
  chain_status: "valid" | "invalid";
}

export interface LedgerPage {
  total: number;
  limit: number;
  offset: number;
  entries: LedgerEntry[];
}

export interface LedgerVerifyResult {
  is_valid: boolean;
  total_entries: number;
  broken_links: string[];
  last_verified_at: string;
}

// --- Owner dashboard types (Phase 7) ---------------------------------------
export interface MetricCard {
  key: string;
  label: string;
  value: number;
  unit: "IQD" | "%" | "count" | "";
  trend: "up" | "down" | "flat";
  trend_pct: number | null;
}
export interface DashLayer1 {
  generated_at: string;
  cards: MetricCard[];
}
export interface DepartmentRow {
  department: string;
  total_waste_iqd: number;
  risk_count: number;
}
export interface CategorySlice {
  category: string;
  label: string;
  amount_iqd: number;
}
export interface DashLayer2 {
  departments: DepartmentRow[];
  categories: CategorySlice[];
}
export interface CrossRefFinding {
  id: string;
  finding_type: string;
  description: string;
  variance_amount: number | null;
  variance_pct: number | null;
  severity: string;
  status: string;
  created_at: string;
}
export interface AnomalyFinding {
  id: string;
  severity: string;
  title: string;
  description: string;
  financial_impact: number | null;
  status: string;
  created_at: string;
}
export interface DashLayer3 {
  narratives: Array<{ audience?: string; text?: string; generated_at?: string }>;
  cross_reference_findings: CrossRefFinding[];
  anomalies: AnomalyFinding[];
}
export interface CertificationBrief {
  id: string;
  auditor_id: string;
  auditor_name: string | null;
  is_valid: boolean;
  corrections_made: Record<string, unknown> | null;
  certified_at: string;
}
export interface LedgerEntryBrief {
  id: string;
  action: string;
  reason: string | null;
  created_by: string | null;
  created_by_name: string | null;
  current_hash: string;
  created_at: string;
}
export interface DashLayer4 {
  document_id: string;
  original_filename: string;
  file_type: string;
  doc_category: string;
  status: string;
  confidence_score: number | null;
  uploaded_by: string | null;
  uploaded_by_name: string | null;
  original_image_url: string | null;
  extracted_data: Record<string, unknown> | null;
  certifications: CertificationBrief[];
  ledger_entries: LedgerEntryBrief[];
}
