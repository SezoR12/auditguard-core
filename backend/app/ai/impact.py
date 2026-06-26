"""FinancialImpactCalculator — convert findings into IQD waste-map items.

Maps anomalies + cross-reference findings to WasteCategory + amount_iqd.
Pure functions returning waste dicts; orchestrator persists into waste_map_items.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.ai.anomaly import Anomaly
from app.ai.cross_reference import CrossRefFinding
from app.ai.data_quality import QualityFlag


@dataclass
class WasteItem:
    category: str  # financial / operational / human / opportunity
    amount_iqd: float
    department: str
    description: str  # Arabic


# How much of a duplicate / overpayment counts as recoverable waste.
DUPLICATE_RECOVERY = 1.0


def impact_from_anomalies(anomalies: list[Anomaly]) -> list[WasteItem]:
    items: list[WasteItem] = []
    for a in anomalies:
        amt = a.financial_impact or 0.0
        if a.code == "zscore_large_amount" and amt > 0:
            items.append(
                WasteItem(
                    category="financial",
                    amount_iqd=round(amt, 2),
                    department="المشتريات",
                    description=f"دفعة زائدة محتملة: {a.description}",
                )
            )
        elif a.code == "iqr_unit_price_outlier" and amt > 0:
            items.append(
                WasteItem(
                    category="financial",
                    amount_iqd=round(amt, 2),
                    department="المشتريات",
                    description=f"تسعير مرتفع: {a.description}",
                )
            )
        elif a.code == "weekend_spike" and amt > 0:
            items.append(
                WasteItem(
                    category="operational",
                    amount_iqd=round(amt, 2),
                    department="المالية",
                    description=f"معاملة مشبوهة: {a.description}",
                )
            )
    return items


def impact_from_cross_ref(findings: list[CrossRefFinding]) -> list[WasteItem]:
    items: list[WasteItem] = []
    for f in findings:
        if f.finding_type == "procurement_vs_bank" and f.variance_amount:
            items.append(
                WasteItem(
                    category="financial",
                    amount_iqd=round(abs(f.variance_amount), 2),
                    department="المشتريات",
                    description=f"تضارب مالي: {f.description}",
                )
            )
        elif f.finding_type == "procurement_vs_inventory":
            # Missing inventory — value unknown without unit price; record qty gap
            # as operational waste with a 0 placeholder amount if no price.
            qty_gap = abs((f.details or {}).get("procured_qty", 0) - (f.details or {}).get("received_qty", 0))
            items.append(
                WasteItem(
                    category="operational",
                    amount_iqd=round(float(qty_gap), 2),
                    department="المخازن",
                    description=f"نقص في الجرد: {f.description}",
                )
            )
    return items


def impact_from_duplicates(flags: list[QualityFlag], records_by_id: dict) -> list[WasteItem]:
    """Duplicate invoices => duplicate payment risk = sum of duplicated amounts."""
    items: list[WasteItem] = []
    for fl in flags:
        if fl.code != "duplicate_invoice_number":
            continue
        amounts = []
        for doc_id in fl.document_ids:
            rec = records_by_id.get(doc_id)
            if rec and rec.amount:
                amounts.append(rec.amount)
        # Recoverable = all but one copy.
        if len(amounts) > 1:
            recoverable = sum(sorted(amounts)[:-1]) * DUPLICATE_RECOVERY
            if recoverable > 0:
                items.append(
                    WasteItem(
                        category="financial",
                        amount_iqd=round(recoverable, 2),
                        department="المحاسبة",
                        description=f"دفع مكرر محتمل: {fl.description}",
                    )
                )
    return items


def run_impact(
    anomalies: list[Anomaly],
    findings: list[CrossRefFinding],
    flags: list[QualityFlag],
    records_by_id: dict,
) -> list[WasteItem]:
    items: list[WasteItem] = []
    items += impact_from_anomalies(anomalies)
    items += impact_from_cross_ref(findings)
    items += impact_from_duplicates(flags, records_by_id)
    return items
