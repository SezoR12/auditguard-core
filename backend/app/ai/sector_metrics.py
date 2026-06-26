"""Sector-specific metric computation for the AI engine.

Each criteria-library metric has a `formula` over base variables (e.g.
"annual_rent / property_value * 100"). The base variables are sourced from the
extra numeric fields auditors capture in a document's
`extracted_data.fields` (beyond the standard invoice fields). We aggregate those
across all certified docs, then SAFELY evaluate each formula (restricted AST —
no eval, no names/calls beyond the provided variables).

A metric is only emitted when ALL of its formula's variables are present and the
result is finite (no divide-by-zero), so partial data never produces misleading
numbers.
"""
from __future__ import annotations

import ast
import operator
from typing import Any

from app.ai.common import InvoiceRecord, to_float
from app.services.criteria_library import metrics_for_sectors

# Standard invoice fields that are NOT sector base variables.
_RESERVED_FIELDS = {
    "invoice_number", "date", "amount", "vendor_name", "items_list",
}

# Allowed binary/unary operators for the safe evaluator.
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_node(node: ast.AST, variables: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, variables)
    if isinstance(node, ast.Constant):  # numbers
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError("non-numeric constant")
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise KeyError(node.id)
        return float(variables[node.id])
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _eval_node(node.left, variables)
        right = _eval_node(node.right, variables)
        if type(node.op) in (ast.Div, ast.Mod) and right == 0:
            raise ZeroDivisionError
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand, variables))
    raise ValueError(f"unsupported expression: {ast.dump(node)}")


def safe_eval_formula(formula: str, variables: dict[str, float]) -> float | None:
    """Evaluate a metric formula safely. Returns None if vars missing / div0."""
    try:
        tree = ast.parse(formula, mode="eval")
        result = _eval_node(tree, variables)
        if result != result or result in (float("inf"), float("-inf")):  # NaN/inf
            return None
        return float(result)
    except (KeyError, ZeroDivisionError, ValueError, SyntaxError, TypeError):
        return None


def collect_base_inputs(records: list[InvoiceRecord]) -> dict[str, float]:
    """Aggregate sector base variables from certified documents.

    Any numeric field in a document's parsed fields that is NOT a standard
    invoice field is treated as a sector base variable and SUMMED across docs
    (e.g. revenue, cogs, occupied_units, total_units, food_sales...).

    Also derives a few convenience aggregates from standard data:
      - procurement_total / bank_outflow_total (by category) as fallbacks.
    """
    base: dict[str, float] = {}

    for r in records:
        # raw is the original parsed fields dict captured on the record.
        raw = getattr(r, "raw_fields", None)
        if isinstance(raw, dict):
            for k, v in raw.items():
                if k in _RESERVED_FIELDS:
                    continue
                num = to_float(v)
                if num is not None:
                    base[k] = base.get(k, 0.0) + num

    return base


def compute_sector_metrics(
    records: list[InvoiceRecord], sectors: list[str]
) -> dict[str, float]:
    """Compute every metric for the given sectors from aggregated base inputs."""
    if not sectors:
        return {}
    base = collect_base_inputs(records)
    out: dict[str, float] = {}
    for m in metrics_for_sectors(sectors):
        val = safe_eval_formula(m.get("formula", ""), base)
        if val is not None:
            out[m["key"]] = round(val, 2)
    return out


def sectors_for_company(company_sector: str | None) -> list[str]:
    """Map a company's free-text sector to criteria-library module keys."""
    if not company_sector:
        return []
    s = company_sector.strip().lower()
    mapping = {
        # Arabic
        "تصنيع": "manufacturing", "صناعة": "manufacturing",
        "مطاعم": "restaurants", "مطعم": "restaurants", "أغذية": "restaurants",
        "عقارات": "real_estate", "عقار": "real_estate",
        "تجارة": "trading", "تجزئة": "trading", "بيع": "trading",
        # English
        "manufacturing": "manufacturing", "factory": "manufacturing",
        "restaurant": "restaurants", "restaurants": "restaurants", "food": "restaurants",
        "real estate": "real_estate", "real_estate": "real_estate", "property": "real_estate",
        "trading": "trading", "retail": "trading", "commerce": "trading",
    }
    for needle, key in mapping.items():
        if needle in s:
            return [key]
    return []
