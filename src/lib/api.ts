// Thin fetch wrapper for the FastAPI backend.
const API_URL =
  (import.meta.env.VITE_AUDITCORE_API_URL as string | undefined) ?? "http://localhost:8000";

const TOKEN_KEY = "auditcore.access_token";
const REFRESH_KEY = "auditcore.refresh_token";

export const tokens = {
  get access() {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(TOKEN_KEY);
  },
  get refresh() {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(REFRESH_KEY);
  },
  set(access: string, refresh: string) {
    window.localStorage.setItem(TOKEN_KEY, access);
    window.localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_KEY);
  },
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (tokens.access) headers.set("Authorization", `Bearer ${tokens.access}`);

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

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
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
export function uploadDocument(
  file: File,
  docCategory: string,
  branchId: string | null,
  onProgress?: (pct: number) => void,
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    form.append("doc_category", docCategory);
    if (branchId) form.append("branch_id", branchId);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/documents/upload`);
    if (tokens.access) xhr.setRequestHeader("Authorization", `Bearer ${tokens.access}`);

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

export const api = {
  login: (email: string, password: string) =>
    request<TokenPair>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => request<CurrentUser>("/auth/me"),
  refresh: (refresh_token: string) =>
    request<TokenPair>("/auth/refresh", { method: "POST", body: JSON.stringify({ refresh_token }) }),

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
};
