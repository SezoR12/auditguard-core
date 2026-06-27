// Preview-mode fallback data. Used when the FastAPI backend at
// VITE_AUDITCORE_API_URL is unreachable (e.g. in the Lovable preview where
// no Docker stack is running). Returns realistic Arabic sample data so the
// dashboards render instead of showing "Failed to fetch".
//
// Matching is path-prefix based: the first key that `path.startsWith(key)`
// wins. Add new entries as new endpoints are wired up.

const now = new Date().toISOString();

const mocks: Record<string, unknown> = {
  "/auth/me": {
    id: "preview-user",
    email: "owner@auditcore.local",
    full_name: "مستخدم العرض",
    role: "owner",
    company_id: "preview-company",
    branch_id: null,
    is_active: true,
  },

  "/owner/dashboard/layer1": {
    generated_at: now,
    cards: [
      { key: "monthly_waste", label: "الهدر الشهري", value: 12500000, unit: "IQD", trend: "down", trend_pct: 8 },
      { key: "trust_index", label: "مؤشر الثقة", value: 87, unit: "%", trend: "up", trend_pct: 3 },
      { key: "critical_alerts", label: "تنبيهات حرجة", value: 4, unit: "count", trend: "down", trend_pct: 25 },
      { key: "predicted_cash", label: "التدفق النقدي المتوقع", value: 245000000, unit: "IQD", trend: "up", trend_pct: 12 },
      { key: "team_efficiency", label: "كفاءة الفريق", value: 92, unit: "%", trend: "up", trend_pct: 5 },
    ],
  },

  "/owner/dashboard/layer2": {
    departments: [
      { department: "المبيعات", total_waste_iqd: 4500000, risk_count: 2 },
      { department: "المخازن", total_waste_iqd: 3200000, risk_count: 1 },
      { department: "المشتريات", total_waste_iqd: 2800000, risk_count: 3 },
      { department: "العمليات", total_waste_iqd: 2000000, risk_count: 1 },
    ],
    categories: [
      { category: "duplicate", label: "فواتير مكررة", amount_iqd: 5200000 },
      { category: "overcharge", label: "زيادة في السعر", amount_iqd: 4100000 },
      { category: "missing_receipt", label: "إيصالات مفقودة", amount_iqd: 3200000 },
    ],
  },

  "/owner/dashboard/layer3": {
    narratives: [
      { audience: "owner", text: "انخفض الهدر بنسبة 8% مقارنة بالشهر الماضي، مع تركّز المخالفات في قسم المبيعات.", generated_at: now },
    ],
    cross_reference_findings: [],
    anomalies: [],
  },

  "/owner/notifications": { unread_count: 0, items: [] },
  "/owner/daily-digests": [],
  "/owner/auditor-performance": [],
  "/owner/ledger": { total: 0, limit: 50, offset: 0, entries: [] },
  "/owner/ledger/verify": { is_valid: true, total_entries: 0, broken_links: [], last_verified_at: now },
  "/owner/report-requests": [],
  "/owner/custom-reports": [],

  "/manager/widgets": { widgets: [] },

  "/documents/my-uploads": [],
  "/documents/pending-certification": [],
  "/documents/company": [],

  "/tasks/my-tasks": [],

  "/templates/criteria": { modules: [] },
  "/templates": [],
  "/admin/report-requests": [],
};

export function previewMockFor(path: string): unknown | undefined {
  // Strip query string for matching.
  const clean = path.split("?")[0];
  if (clean in mocks) return mocks[clean];
  // Prefix fallback (e.g. /owner/dashboard/layer3?department=...).
  for (const key of Object.keys(mocks)) {
    if (clean.startsWith(key)) return mocks[key];
  }
  return undefined;
}
