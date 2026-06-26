"""Shared helpers for the AI engine: parsing certified-document fields.

All AI modules operate on the structured `extracted_data.fields` produced by the
OCR/certification pipeline. This module normalizes those into typed records so
the analytics code stays clean and testable (pure functions, no DB).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def to_float(value: Any) -> float | None:
    """Best-effort parse of an amount/number (handles Arabic digits, commas)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).translate(_AR_DIGITS)
    s = re.sub(r"[^\d.\-]", "", s)
    if s in ("", "-", ".", "-."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_date(value: Any) -> date | None:
    """Parse common date formats (YYYY/MM/DD, DD/MM/YYYY, with - . /)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).translate(_AR_DIGITS).strip()
    m = re.search(r"(\d{1,4})[\/\-.](\d{1,2})[\/\-.](\d{1,4})", s)
    if not m:
        return None
    a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        if a > 31:  # YYYY/MM/DD
            return date(a, b, c)
        if c > 31:  # DD/MM/YYYY
            return date(c, b, a)
        return date(c if c > 31 else 2000 + c if c < 100 else c, b, a)
    except (ValueError, TypeError):
        return None


@dataclass
class InvoiceRecord:
    document_id: str
    category: str  # invoice / statement / report / etc (doc_category)
    category_key: str | None  # original upload key (bank_statement, inventory_report...)
    invoice_number: str | None
    invoice_seq: int | None  # numeric part of invoice_number, if any
    txn_date: date | None
    amount: float | None
    vendor_name: str | None
    items: list[dict] = field(default_factory=list)
    branch_id: str | None = None


def _seq_from_invoice(num: str | None) -> int | None:
    if not num:
        return None
    digits = re.findall(r"\d+", str(num).translate(_AR_DIGITS))
    if not digits:
        return None
    # Use the longest digit run as the serial.
    return int(max(digits, key=len))


def record_from_document(doc: dict) -> InvoiceRecord:
    """Build an InvoiceRecord from a document dict.

    `doc` shape (subset): id, doc_category, branch_id, extracted_data{fields{...},
    category_key}.
    """
    extracted = doc.get("extracted_data") or {}
    fields = extracted.get("fields", {}) if isinstance(extracted, dict) else {}
    num = fields.get("invoice_number")
    return InvoiceRecord(
        document_id=str(doc.get("id")),
        category=str(doc.get("doc_category")),
        category_key=extracted.get("category_key") if isinstance(extracted, dict) else None,
        invoice_number=num,
        invoice_seq=_seq_from_invoice(num),
        txn_date=parse_date(fields.get("date")),
        amount=to_float(fields.get("amount")),
        vendor_name=(fields.get("vendor_name") or None),
        items=fields.get("items_list") or [],
        branch_id=str(doc["branch_id"]) if doc.get("branch_id") else None,
    )


def records_from_documents(docs: list[dict]) -> list[InvoiceRecord]:
    return [record_from_document(d) for d in docs]
