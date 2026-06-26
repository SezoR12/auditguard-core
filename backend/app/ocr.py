"""OCR extraction helpers (Tesseract, Arabic) + field confidence flagging.

This module holds the *pure* OCR logic so it can be unit-tested without a DB.
The background worker (app/workers/ocr_worker.py) orchestrates decryption and
persistence around these functions.
"""
from __future__ import annotations

import io
import re
from typing import Any

# Confidence thresholds for color-coding fields.
GREEN_MIN = 85.0
YELLOW_MIN = 60.0


def flag_for_confidence(confidence: float | None, value: Any) -> str:
    """Return 'green' | 'yellow' | 'red' for a field.

    Red if value missing/empty OR confidence < 60. Yellow if 60-84.
    Green if >= 85.
    """
    if value in (None, "", [], {}):
        return "red"
    if confidence is None:
        return "red"
    if confidence >= GREEN_MIN:
        return "green"
    if confidence >= YELLOW_MIN:
        return "yellow"
    return "red"


# --- Lightweight field parsers (heuristic; Arabic + Latin friendly) ----------

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_INVOICE_RE = re.compile(
    r"(?:invoice|inv|رقم\s*الفاتورة|فاتورة)\D{0,15}?([A-Za-z0-9][A-Za-z0-9\-\/]{2,})",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"(\d{1,4}[\/\-.]\d{1,2}[\/\-.]\d{1,4})")
_AMOUNT_RE = re.compile(
    r"(?:total|amount|المبلغ|الاجمالي|الإجمالي|المجموع)\D{0,15}"
    r"([\d٠-٩][\d٠-٩.,]{0,15})",
    re.IGNORECASE,
)
_VENDOR_RE = re.compile(
    r"(?:vendor|supplier|seller|المورد|البائع|اسم\s*المورد)\s*[:：]?\s*(.+)",
    re.IGNORECASE,
)


def _norm_digits(s: str) -> str:
    return s.translate(_AR_DIGITS)


def parse_fields(text: str) -> dict[str, Any]:
    """Extract structured invoice fields from raw OCR text.

    Returns a dict with keys: invoice_number, date, amount, vendor_name,
    items_list. Missing fields are None / [].
    """
    text = text or ""
    fields: dict[str, Any] = {
        "invoice_number": None,
        "date": None,
        "amount": None,
        "vendor_name": None,
        "items_list": [],
    }

    m = _INVOICE_RE.search(text)
    if m:
        fields["invoice_number"] = _norm_digits(m.group(1)).strip()
    else:
        # Fallback: an INV-style token anywhere (e.g. "INV-2024-0098").
        fm = re.search(r"\bINV[\-\/]?[A-Za-z0-9\-\/]{2,}", text, re.IGNORECASE)
        if fm:
            fields["invoice_number"] = _norm_digits(fm.group(0)).strip()

    m = _DATE_RE.search(_norm_digits(text))
    if m:
        fields["date"] = m.group(1).strip()

    m = _AMOUNT_RE.search(text)
    if m:
        amt = _norm_digits(m.group(1)).replace(",", "").strip(" .")
        fields["amount"] = amt or None
    else:
        # Fallback: the largest standalone integer (>= 4 digits) as the amount.
        nums = re.findall(r"[\d٠-٩]{4,}", text)
        nums = [_norm_digits(n) for n in nums]
        # Exclude things that look like dates/years already captured.
        candidates = [int(n) for n in nums if n.isdigit()]
        if candidates:
            fields["amount"] = str(max(candidates))

    m = _VENDOR_RE.search(text)
    if m:
        fields["vendor_name"] = m.group(1).strip()[:120]

    # items_list: lines that look like "<desc> ... <number>"
    items: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        im = re.search(r"^(.+?)\s+([\d٠-٩][\d٠-٩.,]{0,12})$", line)
        if im and len(im.group(1)) >= 2:
            desc = im.group(1).strip()
            # skip obvious header/total lines
            if re.search(r"(total|المبلغ|الإجمالي|الاجمالي|المجموع)", desc, re.IGNORECASE):
                continue
            items.append(
                {"description": desc, "value": _norm_digits(im.group(2)).replace(",", "")}
            )
    fields["items_list"] = items[:50]
    return fields


def build_extracted_data(
    fields: dict[str, Any],
    field_confidences: dict[str, float | None],
    overall_confidence: float | None,
    raw_text: str = "",
) -> dict[str, Any]:
    """Combine parsed fields + per-field confidence into the stored structure
    with color_flags. Shape:
        {
          "fields": {invoice_number, date, amount, vendor_name, items_list},
          "confidences": {...},
          "color_flags": {field: green|yellow|red},
          "overall_confidence": float,
          "raw_text": str (truncated),
        }
    """
    color_flags = {
        key: flag_for_confidence(field_confidences.get(key), fields.get(key))
        for key in ("invoice_number", "date", "amount", "vendor_name", "items_list")
    }
    return {
        "fields": fields,
        "confidences": field_confidences,
        "color_flags": color_flags,
        "overall_confidence": overall_confidence,
        "raw_text": (raw_text or "")[:5000],
    }


# --- Tesseract integration (imported lazily so tests don't need it) ----------


def image_to_text_and_conf(image_bytes: bytes, lang: str = "ara+eng") -> tuple[str, float]:
    """Run Tesseract on a single image. Returns (text, avg_confidence 0-100).

    Lazily imports pytesseract/PIL so this module imports even where Tesseract
    isn't installed (e.g. unit tests of the parsers).
    """
    import pytesseract
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    text = pytesseract.image_to_string(img, lang=lang)
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
    confs = [float(c) for c in data.get("conf", []) if str(c).strip() not in ("-1", "")]
    avg = round(sum(confs) / len(confs), 2) if confs else 0.0
    return text, avg


def pdf_to_text_and_conf(pdf_bytes: bytes, lang: str = "ara+eng") -> tuple[str, float]:
    """Convert PDF pages to images (pdf2image/poppler) and OCR each page."""
    from pdf2image import convert_from_bytes

    pages = convert_from_bytes(pdf_bytes)
    texts: list[str] = []
    confs: list[float] = []
    for page in pages:
        buf = io.BytesIO()
        page.save(buf, format="PNG")
        text, conf = image_to_text_and_conf(buf.getvalue(), lang=lang)
        texts.append(text)
        if conf:
            confs.append(conf)
    avg = round(sum(confs) / len(confs), 2) if confs else 0.0
    return "\n".join(texts), avg


def run_ocr(file_bytes: bytes, file_type: str, lang: str = "ara+eng") -> tuple[str, float]:
    """Dispatch OCR based on file_type ('image' or 'pdf')."""
    if file_type == "pdf":
        return pdf_to_text_and_conf(file_bytes, lang=lang)
    return image_to_text_and_conf(file_bytes, lang=lang)
