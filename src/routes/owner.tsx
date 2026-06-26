import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { OwnerShell } from "@/components/OwnerShell";
import { useAutoRefresh } from "@/hooks/useAutoRefresh";
import { api, type MetricCard } from "@/lib/api";
import { formatMetric, trendArrow, trendIsPositive } from "@/lib/format";

export const Route = createFileRoute("/owner")({
  head: () => ({ meta: [{ title: "لوحة المالك — AuditCore" }] }),
  component: OwnerLayer1,
});

// Which Layer-2/3 route each card drills into.
const CARD_DRILL: Record<string, string> = {
  monthly_waste: "/owner/departments",
  trust_index: "/owner/analytics",
  critical_alerts: "/owner/analytics",
  predicted_cash: "/owner/analytics",
  team_efficiency: "/owner/performance",
};

function Card({ card, onDrill }: { card: MetricCard; onDrill: () => void }) {
  const positive = trendIsPositive(card.key, card.trend);
  const accent =
    card.key === "monthly_waste" || card.key === "critical_alerts"
      ? "text-red-600"
      : card.key === "trust_index" || card.key === "team_efficiency"
        ? "text-blue-600"
        : "text-foreground";
  return (
    <div className="flex flex-col justify-between rounded-2xl border border-border bg-card p-5 shadow-sm">
      <div className="flex items-start justify-between">
        <span className="text-sm text-muted-foreground">{card.label}</span>
        {card.trend !== "flat" && (
          <span className={positive ? "text-green-600" : "text-red-600"} title="الاتجاه">
            {trendArrow(card.trend)}
            {card.trend_pct != null ? ` ${Math.abs(card.trend_pct)}%` : ""}
          </span>
        )}
      </div>
      <div className={`mt-3 text-3xl font-bold ${accent}`}>{formatMetric(card.value, card.unit)}</div>
      <button
        onClick={onDrill}
        className="mt-4 self-start rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90"
      >
        تفاصيل
      </button>
    </div>
  );
}

function OwnerLayer1() {
  const navigate = useNavigate();
  const { data, loading, error, reload } = useAutoRefresh(() => api.dashLayer1());

  return (
    <OwnerShell title="لوحة المالك" subtitle="نظرة تنفيذية على أداء الشركة" onRefresh={reload}>
      {loading && !data ? (
        <p className="py-16 text-center text-muted-foreground">جاري تحليل البيانات...</p>
      ) : error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-right text-sm text-destructive">
          {error}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data?.cards.map((card) => (
            <Card
              key={card.key}
              card={card}
              onDrill={() => void navigate({ to: CARD_DRILL[card.key] ?? "/owner/analytics" })}
            />
          ))}
        </div>
      )}
    </OwnerShell>
  );
}
