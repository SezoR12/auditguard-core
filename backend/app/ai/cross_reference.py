"""CrossReferencer — reconcile procurement vs bank outflows vs inventory.

Pure functions over categorized records; the orchestrator persists findings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ai.common import InvoiceRecord, to_float

BANK_TOLERANCE = 0.01   # 1%
QTY_TOLERANCE = 0.05    # 5%


@dataclass
class CrossRefFinding:
    finding_type: str
    severity: str
    description: str  # Arabic
    variance_amount: float | None
    variance_pct: float | None
    details: dict[str, Any] = field(default_factory=dict)


def _is_procurement(r: InvoiceRecord) -> bool:
    return r.category in ("invoice",) or (r.category_key in ("invoice", "inventory_report"))


def _is_bank(r: InvoiceRecord) -> bool:
    return r.category == "statement" or r.category_key in ("bank_statement", "statement")


def _is_inventory(r: InvoiceRecord) -> bool:
    return r.category_key == "inventory_report" or r.category == "report"


def match_procurement_vs_bank(records: list[InvoiceRecord]) -> list[CrossRefFinding]:
    """Compare total procurement amount vs total bank outflow (1% tolerance)."""
    proc_total = sum(r.amount for r in records if _is_procurement(r) and r.amount)
    bank_total = sum(r.amount for r in records if _is_bank(r) and r.amount)
    findings: list[CrossRefFinding] = []
    if proc_total <= 0 or bank_total <= 0:
        return findings
    variance = proc_total - bank_total
    pct = abs(variance) / max(proc_total, bank_total)
    if pct > BANK_TOLERANCE:
        findings.append(
            CrossRefFinding(
                finding_type="procurement_vs_bank",
                severity="high" if pct > 0.1 else "medium",
                description=(
                    f"تضارب بين إجمالي المشتريات ({proc_total:,.0f} د.ع) "
                    f"والتدفق البنكي الصادر ({bank_total:,.0f} د.ع) "
                    f"بفارق {variance:,.0f} د.ع ({pct*100:.1f}%)"
                ),
                variance_amount=float(variance),
                variance_pct=round(pct * 100, 2),
                details={"procurement_total": proc_total, "bank_total": bank_total},
            )
        )
    return findings


def match_procurement_vs_inventory(records: list[InvoiceRecord]) -> list[CrossRefFinding]:
    """Compare item quantities procured vs received in inventory (5% tolerance).

    Quantities are matched by item description (normalized).
    """
    def collect(pred) -> dict[str, float]:
        agg: dict[str, float] = {}
        for r in records:
            if not pred(r):
                continue
            for it in r.items:
                desc = str(it.get("description", "")).strip()
                qty = to_float(it.get("value"))
                if desc and qty is not None:
                    agg[desc] = agg.get(desc, 0.0) + qty
        return agg

    procured = collect(_is_procurement)
    received = collect(_is_inventory)
    findings: list[CrossRefFinding] = []
    for desc, p_qty in procured.items():
        r_qty = received.get(desc)
        if r_qty is None:
            continue  # nothing to compare against
        if p_qty <= 0:
            continue
        variance = p_qty - r_qty
        pct = abs(variance) / p_qty
        if pct > QTY_TOLERANCE:
            findings.append(
                CrossRefFinding(
                    finding_type="procurement_vs_inventory",
                    severity="high" if pct > 0.2 else "medium",
                    description=(
                        f"تضارب في كمية الصنف '{desc}': تم شراء {p_qty:g} "
                        f"واستلام {r_qty:g} في الجرد (فارق {variance:g}، {pct*100:.1f}%)"
                    ),
                    variance_amount=None,
                    variance_pct=round(pct * 100, 2),
                    details={"item": desc, "procured_qty": p_qty, "received_qty": r_qty},
                )
            )
    return findings


def run_cross_reference(records: list[InvoiceRecord]) -> list[CrossRefFinding]:
    findings: list[CrossRefFinding] = []
    findings += match_procurement_vs_bank(records)
    findings += match_procurement_vs_inventory(records)
    return findings
