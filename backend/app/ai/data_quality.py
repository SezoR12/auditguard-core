"""DataQualityGuard — quality checks on certified documents.

Pure functions over a list of InvoiceRecord; no DB access here.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.ai.common import InvoiceRecord


@dataclass
class QualityFlag:
    code: str
    severity: str  # low / medium / high / critical
    description: str  # Arabic
    document_ids: list[str]
    details: dict[str, Any] | None = None


def _dup_invoice_numbers(records: list[InvoiceRecord]) -> list[QualityFlag]:
    """Duplicate invoice numbers within the same vendor."""
    by_key: dict[tuple, list[InvoiceRecord]] = defaultdict(list)
    for r in records:
        if r.invoice_number:
            by_key[(r.vendor_name or "?", r.invoice_number)].append(r)
    flags: list[QualityFlag] = []
    for (vendor, num), group in by_key.items():
        if len(group) > 1:
            flags.append(
                QualityFlag(
                    code="duplicate_invoice_number",
                    severity="high",
                    description=f"رقم فاتورة مكرر '{num}' للمورد '{vendor}' ({len(group)} نسخ)",
                    document_ids=[r.document_id for r in group],
                    details={"vendor": vendor, "invoice_number": num, "count": len(group)},
                )
            )
    return flags


def _missing_mandatory(records: list[InvoiceRecord]) -> list[QualityFlag]:
    flags: list[QualityFlag] = []
    for r in records:
        missing = []
        if r.txn_date is None:
            missing.append("التاريخ")
        if r.amount is None:
            missing.append("المبلغ")
        if not r.vendor_name:
            missing.append("المورد")
        if missing:
            flags.append(
                QualityFlag(
                    code="missing_mandatory_fields",
                    severity="medium",
                    description=f"حقول إلزامية ناقصة: {'، '.join(missing)}",
                    document_ids=[r.document_id],
                    details={"missing": missing},
                )
            )
    return flags


def _out_of_sequence(records: list[InvoiceRecord]) -> list[QualityFlag]:
    """Gaps / out-of-sequence document serial numbers per vendor."""
    by_vendor: dict[str, list[InvoiceRecord]] = defaultdict(list)
    for r in records:
        if r.invoice_seq is not None:
            by_vendor[r.vendor_name or "?"].append(r)
    flags: list[QualityFlag] = []
    for vendor, group in by_vendor.items():
        seqs = sorted({r.invoice_seq for r in group})
        if len(seqs) < 3:
            continue
        # Detect gaps in an otherwise consecutive run.
        gaps = []
        for a, b in zip(seqs, seqs[1:]):
            if 1 < (b - a) <= 100:  # ignore huge jumps (different schemes)
                gaps.extend(range(a + 1, b))
        if gaps:
            flags.append(
                QualityFlag(
                    code="out_of_sequence",
                    severity="medium",
                    description=f"أرقام مستندات مفقودة في تسلسل المورد '{vendor}': {gaps[:10]}",
                    document_ids=[r.document_id for r in group],
                    details={"vendor": vendor, "missing_serials": gaps[:50]},
                )
            )
    return flags


def _amount_consistency(records: list[InvoiceRecord]) -> list[QualityFlag]:
    """Circular/inconsistent references: amount present but non-positive / zero."""
    flags: list[QualityFlag] = []
    for r in records:
        if r.amount is not None and r.amount <= 0:
            flags.append(
                QualityFlag(
                    code="invalid_amount",
                    severity="medium",
                    description=f"قيمة مبلغ غير منطقية: {r.amount}",
                    document_ids=[r.document_id],
                    details={"amount": r.amount},
                )
            )
    return flags


def run_data_quality(records: list[InvoiceRecord]) -> list[QualityFlag]:
    """Run all quality checks and return flags."""
    flags: list[QualityFlag] = []
    flags += _dup_invoice_numbers(records)
    flags += _missing_mandatory(records)
    flags += _out_of_sequence(records)
    flags += _amount_consistency(records)
    return flags


def quality_score(records: list[InvoiceRecord], flags: list[QualityFlag]) -> float:
    """0–100 data-quality score: clean docs / total, weighted by severity."""
    if not records:
        return 0.0
    weights = {"low": 0.25, "medium": 0.5, "high": 1.0, "critical": 1.5}
    flagged_docs = sum(weights.get(f.severity, 0.5) * len(f.document_ids) for f in flags)
    total = len(records)
    score = max(0.0, 100.0 * (1 - flagged_docs / (total * 2)))
    return round(min(100.0, score), 2)
