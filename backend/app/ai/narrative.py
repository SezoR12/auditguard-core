"""NarrativeGenerator — template-based Arabic narratives (no LLM, on-prem).

Produces role-specific summaries from the analysis results.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.ai.anomaly import Anomaly
from app.ai.cross_reference import CrossRefFinding
from app.ai.impact import WasteItem


@dataclass
class Narrative:
    audience: str  # owner / manager
    text: str  # Arabic


def owner_narrative(
    waste_items: list[WasteItem],
    findings: list[CrossRefFinding],
    anomalies: list[Anomaly],
) -> Narrative:
    total_waste = sum(w.amount_iqd for w in waste_items if w.category == "financial")
    lines: list[str] = []
    if total_waste > 0:
        dept = "المشتريات"
        # pick the department with the largest financial waste
        by_dept: dict[str, float] = {}
        for w in waste_items:
            if w.category == "financial":
                by_dept[w.department] = by_dept.get(w.department, 0) + w.amount_iqd
        if by_dept:
            dept = max(by_dept, key=by_dept.get)
        lines.append(
            f"تم رصد هدر بقيمة {total_waste:,.0f} د.ع في قسم {dept} "
            f"نتيجة تضارب الفواتير مع الجرد والتدفقات البنكية."
        )
    if anomalies:
        lines.append(f"تم اكتشاف {len(anomalies)} حالة شاذة في الأرقام المالية.")
    if findings:
        lines.append(f"يوجد {len(findings)} تضارب في المطابقة المرجعية يحتاج إلى مراجعة.")
    if not lines:
        lines.append("لم يتم رصد أي هدر أو مخاطر جوهرية في بيانات اليوم.")
    return Narrative(audience="owner", text=" ".join(lines))


def manager_narrative(open_corrections: int, department: str = "المبيعات") -> Narrative:
    if open_corrections > 0:
        text = f"يوجد لديك {open_corrections} مهمة تصحيح مفتوحة في قسم {department}."
    else:
        text = f"لا توجد مهام تصحيح مفتوحة حالياً في قسم {department}."
    return Narrative(audience="manager", text=text)


def run_narratives(
    waste_items: list[WasteItem],
    findings: list[CrossRefFinding],
    anomalies: list[Anomaly],
    open_corrections: int,
) -> list[Narrative]:
    return [
        owner_narrative(waste_items, findings, anomalies),
        manager_narrative(open_corrections),
    ]
