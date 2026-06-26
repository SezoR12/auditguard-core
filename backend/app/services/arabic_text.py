"""Arabic shaping helpers for PDF/PNG rendering.

reportlab and matplotlib don't shape/bidi Arabic, so we reshape (connect
letters) and apply the bidi algorithm before drawing. Excel/HTML don't need
this (the rendering engine handles it).
"""
from __future__ import annotations


def shape_arabic(text: str) -> str:
    """Return display-ready (reshaped + bidi-reordered) Arabic text."""
    if not text:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:  # noqa: BLE001 - libs missing -> best effort
        return str(text)


def has_arabic(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" for ch in str(text or ""))
