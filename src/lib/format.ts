// Shared formatting helpers for the dashboard (Arabic-friendly).

export function formatIQD(v: number): string {
  return new Intl.NumberFormat("ar-IQ", { maximumFractionDigits: 0 }).format(v) + " د.ع";
}

export function formatNumber(v: number): string {
  return new Intl.NumberFormat("ar-IQ", { maximumFractionDigits: 1 }).format(v);
}

export function formatMetric(value: number, unit: string): string {
  if (unit === "IQD") return formatIQD(value);
  if (unit === "%") return `${formatNumber(value)}%`;
  return formatNumber(value);
}

export function trendArrow(trend: string): string {
  if (trend === "up") return "▲";
  if (trend === "down") return "▼";
  return "■";
}

export function formatDate(iso: string): string {
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

// Whether a higher value is "good" (green) for the trend coloring.
export function trendIsPositive(key: string, trend: string): boolean {
  const higherIsBetter = key === "trust_index" || key === "team_efficiency";
  if (trend === "flat") return true;
  return higherIsBetter ? trend === "up" : trend === "down";
}
