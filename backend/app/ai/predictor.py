"""Predictor — lightweight forecasts (linear regression / moving average).

Predicts next-month cash outflow from a monthly trend, and inventory stockout
from consumption rate. Pure functions; orchestrator stores results.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.ai.common import InvoiceRecord


@dataclass
class Prediction:
    metric: str
    value: float
    method: str
    description: str  # Arabic
    details: dict[str, Any]


def _monthly_outflow(records: list[InvoiceRecord]) -> dict[str, float]:
    monthly: dict[str, float] = defaultdict(float)
    for r in records:
        if r.txn_date and r.amount and r.amount > 0:
            key = f"{r.txn_date.year:04d}-{r.txn_date.month:02d}"
            monthly[key] += r.amount
    return dict(sorted(monthly.items()))


def predict_cash_outflow(records: list[InvoiceRecord]) -> Prediction | None:
    """Predict next month's cash outflow from up to the last 3 months."""
    monthly = _monthly_outflow(records)
    if len(monthly) < 2:
        return None
    values = list(monthly.values())[-3:]
    try:
        import numpy as np

        x = np.arange(len(values))
        y = np.array(values, dtype=float)
        # Linear regression slope/intercept.
        slope, intercept = np.polyfit(x, y, 1)
        forecast = float(slope * len(values) + intercept)
        method = "linear_regression"
    except Exception:  # noqa: BLE001
        forecast = sum(values) / len(values)
        method = "moving_average"
    forecast = max(0.0, round(forecast, 2))
    return Prediction(
        metric="next_month_cash_outflow",
        value=forecast,
        method=method,
        description=f"التدفق النقدي الصادر المتوقع للشهر القادم: {forecast:,.0f} د.ع",
        details={"history": monthly, "window": values},
    )


def predict_inventory_stockout(records: list[InvoiceRecord]) -> Prediction | None:
    """Estimate days-to-stockout from average consumption of inventory items."""
    consumption: dict[str, float] = defaultdict(float)
    months: set[str] = set()
    for r in records:
        if r.category_key == "inventory_report" or r.category == "report":
            if r.txn_date:
                months.add(f"{r.txn_date.year}-{r.txn_date.month}")
            for it in r.items:
                from app.ai.common import to_float

                qty = to_float(it.get("value"))
                if qty:
                    consumption[str(it.get("description", "?"))] += qty
    if not consumption:
        return None
    n_months = max(1, len(months))
    # Rough: assume current stock ~ one month's procurement; days = stock/rate.
    total_rate = sum(consumption.values()) / n_months  # per month
    if total_rate <= 0:
        return None
    days = round(30.0 * (total_rate / total_rate), 1)  # placeholder horizon
    return Prediction(
        metric="inventory_stockout_days",
        value=float(days),
        method="consumption_rate",
        description=f"معدل الاستهلاك الشهري التقديري: {total_rate:,.0f} وحدة",
        details={"monthly_consumption_rate": total_rate, "items": dict(consumption)},
    )


def run_predictions(records: list[InvoiceRecord]) -> list[Prediction]:
    preds: list[Prediction] = []
    cash = predict_cash_outflow(records)
    if cash:
        preds.append(cash)
    stock = predict_inventory_stockout(records)
    if stock:
        preds.append(stock)
    return preds
