"""Sector criteria library.

Each module is a JSON-able schema describing the sector-specific metrics a
template can bind to, and (for the AI engine) which calculations to run. The
Template Builder offers these as toggles; the renderer resolves bound fields
against the company's analytics + a computed metrics map.
"""
from __future__ import annotations

# Each metric: key, Arabic label, unit, and a "source" hint telling the engine
# how to compute it. `formula` is a documented expression over base aggregates;
# the MVP renderer fills these from analytics_outputs.data or returns 0.
CRITERIA_MODULES: dict[str, dict] = {
    "manufacturing": {
        "label": "التصنيع",
        "metrics": [
            {"key": "oee", "label": "الكفاءة الكلية للمعدات (OEE)", "unit": "%",
             "formula": "availability * performance * quality"},
            {"key": "defect_rate", "label": "معدل العيوب", "unit": "%",
             "formula": "defective_units / total_units * 100"},
        ],
    },
    "restaurants": {
        "label": "المطاعم",
        "metrics": [
            {"key": "food_cost", "label": "نسبة تكلفة الطعام", "unit": "%",
             "formula": "food_cost / food_sales * 100"},
            {"key": "table_turnover", "label": "معدل دوران الطاولات", "unit": "x",
             "formula": "covers / seats"},
        ],
    },
    "real_estate": {
        "label": "العقارات",
        "metrics": [
            {"key": "rental_yield", "label": "العائد الإيجاري", "unit": "%",
             "formula": "annual_rent / property_value * 100"},
            {"key": "occupancy_rate", "label": "نسبة الإشغال", "unit": "%",
             "formula": "occupied_units / total_units * 100"},
            {"key": "vacancy_rate", "label": "نسبة الشغور", "unit": "%",
             "formula": "vacant_units / total_units * 100"},
        ],
    },
    "trading": {
        "label": "التجارة",
        "metrics": [
            {"key": "inventory_turnover", "label": "معدل دوران المخزون", "unit": "x",
             "formula": "cogs / avg_inventory"},
            {"key": "margin", "label": "هامش الربح", "unit": "%",
             "formula": "(revenue - cogs) / revenue * 100"},
        ],
    },
}


def list_modules() -> list[dict]:
    """Catalog for the Template Builder UI (sector → metrics)."""
    return [
        {"sector": key, "label": mod["label"], "metrics": mod["metrics"]}
        for key, mod in CRITERIA_MODULES.items()
    ]


def get_module(sector: str) -> dict | None:
    return CRITERIA_MODULES.get(sector)


def metrics_for_sectors(sectors: list[str]) -> list[dict]:
    """Flatten the metrics across the selected sector modules."""
    out: list[dict] = []
    for s in sectors:
        mod = CRITERIA_MODULES.get(s)
        if mod:
            for m in mod["metrics"]:
                out.append({**m, "sector": s})
    return out
