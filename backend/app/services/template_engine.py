"""No-code template rendering engine.

A template `config` is JSON describing an ordered list of blocks:

    {
      "title": "تقرير العقارات",
      "blocks": [
        {"type": "text", "content": "ملخص الأداء"},
        {"type": "metric", "binding": "trust_index", "label": "مؤشر الثقة"},
        {"type": "metric", "binding": "occupancy_rate", "label": "نسبة الإشغال"},
        {"type": "table", "source": "waste_map_items",
         "columns": ["department","category","amount_iqd","status"]},
        {"type": "chart", "source": "waste_by_department"},
        {"type": "image", "placeholder": "شعار الشركة"}
      ]
    }

`resolve_data` builds a live data context from the company's DB rows + sector
criteria; `render_pdf` renders the blocks to a PDF using the bundled Amiri font.
Sector metric values come from the latest analytics_outputs snapshot's
`data.sector_metrics` if present, else 0 (the AI engine populates these when the
template's sectors are active).
"""
from __future__ import annotations

import io
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalyticsOutput, RiskAlert, WasteMapItem
from app.models.enums import OutputType
from app.services.arabic_text import shape_arabic
from app.services.criteria_library import metrics_for_sectors
from app.services.export_service import FONT_PATH

DUMMY = {
    "company_name": "شركة تجريبية",
    "metrics": {"trust_index": 87, "occupancy_rate": 92, "rental_yield": 7.5,
                "oee": 78, "food_cost": 31, "inventory_turnover": 5.2, "margin": 24},
    "waste_rows": [["المشتريات", "مالي", 1500000, "مفتوح"],
                   ["المخازن", "تشغيلي", 900000, "مفتوح"]],
    "waste_by_department": [("المشتريات", 1500000), ("المخازن", 900000)],
}


async def resolve_data(
    session: AsyncSession, company_id: uuid.UUID, sectors: list[str] | None
) -> dict[str, Any]:
    """Build the live data context a template binds against."""
    sectors = sectors or []

    # Latest snapshot (trust index + any sector metrics the engine stored).
    snap = (
        await session.execute(
            select(AnalyticsOutput)
            .where(
                AnalyticsOutput.company_id == company_id,
                AnalyticsOutput.output_type == OutputType.daily_snapshot,
            )
            .order_by(AnalyticsOutput.generated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    snap_data = snap.data if (snap and isinstance(snap.data, dict)) else {}
    stored_metrics = snap_data.get("sector_metrics", {}) if isinstance(snap_data, dict) else {}

    metrics: dict[str, Any] = {"trust_index": snap.trust_index if snap else 0}
    for m in metrics_for_sectors(sectors):
        metrics[m["key"]] = stored_metrics.get(m["key"], 0)

    # Waste rows for table/chart blocks.
    waste = (
        await session.execute(
            select(WasteMapItem)
            .where(WasteMapItem.company_id == company_id)
            .order_by(WasteMapItem.amount_iqd.desc())
            .limit(200)
        )
    ).scalars().all()
    waste_rows = [
        [w.department, w.category.value if hasattr(w.category, "value") else str(w.category),
         float(w.amount_iqd), w.status]
        for w in waste
    ]

    by_dept = (
        await session.execute(
            select(WasteMapItem.department, func.coalesce(func.sum(WasteMapItem.amount_iqd), 0))
            .where(WasteMapItem.company_id == company_id)
            .group_by(WasteMapItem.department)
            .order_by(func.sum(WasteMapItem.amount_iqd).desc())
        )
    ).all()

    risk_count = (
        await session.execute(
            select(func.count()).select_from(RiskAlert).where(RiskAlert.company_id == company_id)
        )
    ).scalar_one()

    return {
        "metrics": metrics,
        "waste_rows": waste_rows,
        "waste_by_department": [(d or "غير محدد", float(v)) for d, v in by_dept],
        "risk_count": int(risk_count),
    }


def _column_label(col: str) -> str:
    return {
        "department": "القسم", "category": "الفئة", "amount_iqd": "المبلغ (د.ع)",
        "status": "الحالة", "title": "العنوان", "severity": "الخطورة",
    }.get(col, col)


def render_pdf(config: dict, data: dict, *, title: str | None = None) -> bytes:
    """Render a template config + data context into a PDF (Arabic, RTL)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    pdfmetrics.registerFont(TTFont("Amiri", FONT_PATH))
    styles = getSampleStyleSheet()
    st_title = ParagraphStyle("t", parent=styles["Title"], fontName="Amiri", alignment=2)
    st_h = ParagraphStyle("h", parent=styles["Heading2"], fontName="Amiri", alignment=2)
    st_n = ParagraphStyle("n", parent=styles["Normal"], fontName="Amiri", alignment=2, fontSize=11)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm)
    el: list = [Paragraph(shape_arabic(title or config.get("title", "تقرير مخصص")), st_title),
                Spacer(1, 6 * mm)]

    metrics = data.get("metrics", {})
    for block in config.get("blocks", []):
        btype = block.get("type")
        if btype == "text":
            el.append(Paragraph(shape_arabic(str(block.get("content", ""))), st_n))
            el.append(Spacer(1, 3 * mm))
        elif btype == "metric":
            key = block.get("binding")
            label = block.get("label", key)
            val = metrics.get(key, 0)
            el.append(Paragraph(shape_arabic(f"{label}: {val}"), st_h))
            el.append(Spacer(1, 2 * mm))
        elif btype == "table":
            cols = block.get("columns", ["department", "category", "amount_iqd", "status"])
            rows = data.get("waste_rows", [])
            head = [Paragraph(shape_arabic(_column_label(c)), st_n) for c in reversed(cols)]
            table_data = [head]
            for r in rows[:100]:
                table_data.append([Paragraph(shape_arabic(str(c)), st_n) for c in reversed(r[: len(cols)])])
            t = Table(table_data, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("FONTNAME", (0, 0), (-1, -1), "Amiri"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ]))
            el.append(t)
            el.append(Spacer(1, 5 * mm))
        elif btype == "chart":
            png = _chart_png(data.get(block.get("source", "waste_by_department"), []))
            if png:
                el.append(Image(io.BytesIO(png), width=160 * mm, height=90 * mm))
                el.append(Spacer(1, 5 * mm))
        elif btype == "image":
            el.append(Paragraph(shape_arabic(f"[{block.get('placeholder', 'صورة')}]"), st_n))
            el.append(Spacer(1, 3 * mm))

    doc.build(el)
    return buf.getvalue()


def _chart_png(pairs: list) -> bytes | None:
    if not pairs:
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.font_manager as fm
    import matplotlib.pyplot as plt

    fm.fontManager.addfont(FONT_PATH)
    prop = fm.FontProperties(fname=FONT_PATH)
    labels = [shape_arabic(str(p[0])) for p in pairs[:12]]
    values = [float(p[1]) for p in pairs[:12]]
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=200)
    ax.bar(range(len(values)), values, color="#dc2626")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontproperties=prop, rotation=30, ha="right")
    fig.tight_layout()
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    return b.getvalue()
