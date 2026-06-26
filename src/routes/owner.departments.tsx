import { createFileRoute, useNavigate } from "@tanstack/react-router";
import {
  Bar,
  BarChart,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { OwnerShell } from "@/components/OwnerShell";
import { ExportButtons } from "@/components/ExportButtons";
import { useAutoRefresh } from "@/hooks/useAutoRefresh";
import { api } from "@/lib/api";
import { formatIQD } from "@/lib/format";

export const Route = createFileRoute("/owner/departments")({
  head: () => ({ meta: [{ title: "توزيع الأقسام — AuditCore" }] }),
  component: OwnerLayer2,
});

const CATEGORY_COLORS: Record<string, string> = {
  financial: "#dc2626", // red
  operational: "#f59e0b", // amber
  human: "#6366f1", // indigo
  opportunity: "#16a34a", // green
};

function OwnerLayer2() {
  const navigate = useNavigate();
  const { data, loading, error, reload } = useAutoRefresh(() => api.dashLayer2());

  return (
    <OwnerShell title="توزيع الهدر والمخاطر حسب الأقسام" subtitle="انقر على أي قسم لعرض التفاصيل" onRefresh={reload}>
      {loading && !data ? (
        <p className="py-16 text-center text-muted-foreground">جاري تحليل البيانات...</p>
      ) : error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-right text-sm text-destructive">{error}</div>
      ) : (
        <div className="space-y-6">
          <div className="flex justify-end">
            <ExportButtons outputType="waste_map" />
          </div>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Bar chart: waste by department */}
            <section className="rounded-xl border border-border bg-card p-4">
              <h2 className="mb-3 text-sm font-semibold text-foreground">الهدر حسب القسم</h2>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={data?.departments ?? []}>
                  <XAxis dataKey="department" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => formatIQD(v)} />
                  <Bar dataKey="total_waste_iqd" name="الهدر (د.ع)" fill="#dc2626" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </section>

            {/* Pie chart: category share */}
            <section className="rounded-xl border border-border bg-card p-4">
              <h2 className="mb-3 text-sm font-semibold text-foreground">نسبة الفئات</h2>
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={data?.categories ?? []}
                    dataKey="amount_iqd"
                    nameKey="label"
                    cx="50%"
                    cy="50%"
                    outerRadius={90}
                    label={(e) => e.label}
                  >
                    {(data?.categories ?? []).map((c) => (
                      <Cell key={c.category} fill={CATEGORY_COLORS[c.category] ?? "#94a3b8"} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: number) => formatIQD(v)} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </section>
          </div>

          {/* Ranked table */}
          <section className="overflow-hidden rounded-xl border border-border bg-card">
            <h2 className="border-b border-border px-4 py-3 text-sm font-semibold text-foreground">
              الأقسام مرتبة حسب الهدر
            </h2>
            {(data?.departments ?? []).length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-muted-foreground">لا توجد بيانات</p>
            ) : (
              <table className="w-full text-right text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-muted-foreground">
                    <th className="px-4 py-2 font-medium">القسم</th>
                    <th className="px-4 py-2 font-medium">إجمالي الهدر</th>
                    <th className="px-4 py-2 font-medium">عدد البنود</th>
                    <th className="px-4 py-2 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {data?.departments.map((d) => (
                    <tr key={d.department} className="border-b border-border/50 last:border-0">
                      <td className="px-4 py-2 text-foreground">{d.department}</td>
                      <td className="px-4 py-2 text-red-600">{formatIQD(d.total_waste_iqd)}</td>
                      <td className="px-4 py-2 text-muted-foreground">{d.risk_count}</td>
                      <td className="px-4 py-2">
                        <button
                          onClick={() =>
                            void navigate({ to: "/owner/analytics", search: { department: d.department } })
                          }
                          className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:opacity-90"
                        >
                          عرض التحليل
                        </button>
                      </td>
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
