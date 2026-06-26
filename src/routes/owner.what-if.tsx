import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { OwnerShell } from "@/components/OwnerShell";
import { ExportButtons } from "@/components/ExportButtons";
import { api, type WhatIfResult } from "@/lib/api";
import { formatIQD } from "@/lib/format";

export const Route = createFileRoute("/owner/what-if")({
  head: () => ({ meta: [{ title: "محاكي ماذا لو — AuditCore" }] }),
  component: WhatIfPage,
});

function WhatIfPage() {
  const [baseAmount, setBaseAmount] = useState(1_000_000);
  const [recovery, setRecovery] = useState(50);
  const [months, setMonths] = useState(3);
  const [cost, setCost] = useState(100_000);
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    setError(null);
    try {
      setResult(
        await api.whatIf({
          base_amount_iqd: baseAmount,
          recovery_pct: recovery,
          implementation_months: months,
          implementation_cost_iqd: cost,
          horizon_months: 6,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "خطأ في المحاكاة");
    }
  }, [baseAmount, recovery, months, cost]);

  // Live recompute (debounced).
  useEffect(() => {
    const id = setTimeout(() => void run(), 250);
    return () => clearTimeout(id);
  }, [run]);

  const chartData =
    result?.projection.map((p) => ({ name: `${p.month}`, value: p.cumulative_cash_flow })) ?? [];

  return (
    <OwnerShell title="محاكي ماذا لو" subtitle="حلّل أثر استرداد الهدر على التدفق النقدي وصافي الربح">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Inputs */}
        <section className="space-y-5 rounded-xl border border-border bg-card p-5">
          <div>
            <label className="mb-1 block text-sm text-muted-foreground">المبلغ الأساسي (د.ع)</label>
            <input
              type="number"
              value={baseAmount}
              onChange={(e) => setBaseAmount(Number(e.target.value))}
              dir="ltr"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-right text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-muted-foreground">
              نسبة الاسترداد المتوقعة: {recovery}%
            </label>
            <input type="range" min={0} max={100} value={recovery} onChange={(e) => setRecovery(Number(e.target.value))} className="w-full" />
          </div>
          <div>
            <label className="mb-1 block text-sm text-muted-foreground">مدة التنفيذ: {months} شهر</label>
            <input type="range" min={1} max={12} value={months} onChange={(e) => setMonths(Number(e.target.value))} className="w-full" />
          </div>
          <div>
            <label className="mb-1 block text-sm text-muted-foreground">تكلفة التنفيذ (د.ع)</label>
            <input
              type="number"
              value={cost}
              onChange={(e) => setCost(Number(e.target.value))}
              dir="ltr"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-right text-sm"
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </section>

        {/* Results */}
        <section className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="text-xs text-muted-foreground">المبلغ المسترد</div>
              <div className="mt-1 text-xl font-bold text-green-600">{formatIQD(result?.recovered_amount ?? 0)}</div>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <div className="text-xs text-muted-foreground">أثر التدفق النقدي الشهري</div>
              <div className={`mt-1 text-xl font-bold ${(result?.monthly_cash_flow_impact ?? 0) >= 0 ? "text-green-600" : "text-destructive"}`}>
                {formatIQD(result?.monthly_cash_flow_impact ?? 0)}
              </div>
            </div>
            <div className="rounded-xl border border-border bg-card p-4 sm:col-span-2">
              <div className="text-xs text-muted-foreground">أثر صافي الربح</div>
              <div className={`mt-1 text-2xl font-bold ${(result?.net_profit_impact ?? 0) >= 0 ? "text-green-600" : "text-destructive"}`}>
                {formatIQD(result?.net_profit_impact ?? 0)}
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-border bg-card p-4">
            <h3 className="mb-3 text-sm font-semibold text-foreground">إسقاط 6 أشهر — التدفق النقدي التراكمي</h3>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={chartData}>
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip formatter={(v: number) => formatIQD(v)} labelFormatter={(l) => `الشهر ${l}`} />
                <Line type="monotone" dataKey="value" stroke="#2563eb" strokeWidth={2} dot />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="flex justify-end">
            <ExportButtons outputType="analytics" />
          </div>
        </section>
      </div>
    </OwnerShell>
  );
}
