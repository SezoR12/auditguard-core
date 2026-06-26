"""AnomalyDetector — statistical anomaly detection over certified figures.

Needs >= 30 records for a statistical baseline; otherwise most checks are
skipped (returns []). Pure functions returning anomaly dicts; the orchestrator
persists them into risk_alerts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai.common import InvoiceRecord

MIN_BASELINE = 30
Z_THRESHOLD = 3.0


@dataclass
class Anomaly:
    code: str
    severity: str  # high / critical
    title: str
    description: str
    financial_impact: float | None
    document_ids: list[str]
    details: dict[str, Any] | None = None


def _zscore_outliers(records: list[InvoiceRecord]) -> list[Anomaly]:
    import numpy as np

    amounts = [(r.document_id, r.amount) for r in records if r.amount is not None and r.amount > 0]
    if len(amounts) < MIN_BASELINE:
        return []
    vals = np.array([a for _, a in amounts], dtype=float)
    mean = vals.mean()
    std = vals.std(ddof=0)
    if std == 0:
        return []
    out: list[Anomaly] = []
    for (doc_id, amt) in amounts:
        z = (amt - mean) / std
        if z > Z_THRESHOLD:
            out.append(
                Anomaly(
                    code="zscore_large_amount",
                    severity="critical" if z > 5 else "high",
                    title="مبلغ غير اعتيادي (مرتفع جداً)",
                    description=f"مبلغ {amt:,.0f} د.ع يتجاوز المتوسط بمقدار {z:.1f} انحراف معياري",
                    financial_impact=float(amt - mean),
                    document_ids=[doc_id],
                    details={"amount": amt, "mean": float(mean), "z": round(float(z), 2)},
                )
            )
    return out


def _iqr_unit_price_outliers(records: list[InvoiceRecord]) -> list[Anomaly]:
    import numpy as np

    from app.ai.common import to_float

    prices: list[tuple[str, float]] = []
    for r in records:
        for it in r.items:
            v = to_float(it.get("value"))
            if v is not None and v > 0:
                prices.append((r.document_id, v))
    if len(prices) < MIN_BASELINE:
        return []
    vals = np.array([p for _, p in prices], dtype=float)
    q1, q3 = np.percentile(vals, [25, 75])
    iqr = q3 - q1
    if iqr == 0:
        return []
    upper = q3 + 1.5 * iqr
    out: list[Anomaly] = []
    seen: set[str] = set()
    for (doc_id, v) in prices:
        if v > upper and doc_id not in seen:
            seen.add(doc_id)
            out.append(
                Anomaly(
                    code="iqr_unit_price_outlier",
                    severity="high",
                    title="سعر وحدة شاذ",
                    description=f"سعر وحدة {v:,.0f} د.ع يتجاوز الحد الأعلى ({upper:,.0f})",
                    financial_impact=float(v - q3),
                    document_ids=[doc_id],
                    details={"value": v, "upper_bound": float(upper)},
                )
            )
    return out


def _serial_gaps(records: list[InvoiceRecord]) -> list[Anomaly]:
    """Gaps in serial invoice numbers (potential missing/suppressed invoices)."""
    from collections import defaultdict

    by_vendor: dict[str, list[int]] = defaultdict(list)
    for r in records:
        if r.invoice_seq is not None:
            by_vendor[r.vendor_name or "?"].append(r.invoice_seq)
    out: list[Anomaly] = []
    for vendor, seqs in by_vendor.items():
        s = sorted(set(seqs))
        if len(s) < 5:
            continue
        gaps = [n for a, b in zip(s, s[1:]) if 1 < (b - a) <= 50 for n in range(a + 1, b)]
        if gaps:
            out.append(
                Anomaly(
                    code="serial_gap",
                    severity="high",
                    title="فجوات في تسلسل أرقام الفواتير",
                    description=f"فواتير مفقودة محتملة للمورد '{vendor}': {gaps[:10]}",
                    financial_impact=None,
                    document_ids=[],
                    details={"vendor": vendor, "missing": gaps[:50]},
                )
            )
    return out


def _weekend_spikes(records: list[InvoiceRecord]) -> list[Anomaly]:
    """Weekend transaction spikes (Fri/Sat in Iraq) — flag unusual volume."""
    import numpy as np

    dated = [(r.document_id, r.txn_date, r.amount) for r in records if r.txn_date]
    if len(dated) < MIN_BASELINE:
        return []
    # Iraqi weekend = Friday(4), Saturday(5)
    weekend = [(d_id, amt) for d_id, dt, amt in dated if dt.weekday() in (4, 5) and amt]
    weekday_amts = [amt for _, dt, amt in dated if dt.weekday() not in (4, 5) and amt]
    if not weekend or len(weekday_amts) < 10:
        return []
    wk_mean = float(np.mean(weekday_amts))
    out: list[Anomaly] = []
    for d_id, amt in weekend:
        if amt > wk_mean * 3:
            out.append(
                Anomaly(
                    code="weekend_spike",
                    severity="high",
                    title="معاملة كبيرة في عطلة نهاية الأسبوع",
                    description=f"معاملة بقيمة {amt:,.0f} د.ع في يوم عطلة (تتجاوز 3x متوسط أيام العمل)",
                    financial_impact=float(amt - wk_mean),
                    document_ids=[d_id],
                    details={"amount": amt, "weekday_mean": wk_mean},
                )
            )
    return out


def run_anomaly_detection(records: list[InvoiceRecord]) -> list[Anomaly]:
    """Run statistical anomaly checks. Returns [] if below baseline size."""
    anomalies: list[Anomaly] = []
    anomalies += _zscore_outliers(records)
    anomalies += _iqr_unit_price_outliers(records)
    anomalies += _serial_gaps(records)
    anomalies += _weekend_spikes(records)
    return anomalies
