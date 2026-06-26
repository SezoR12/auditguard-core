"""Owner 4-layer dashboard API.

Layer 1: aggregated executive metrics (5 cards)
Layer 2: department + category breakdown
Layer 3: AI findings (narratives, cross-ref, anomalies)
Layer 4: raw document + certifications + ledger (full transparency)

All endpoints are owner/management only (require_role). Because the underlying
analytics/waste/risk/cross_ref tables are RLS-protected and the session binds
the caller's role, an auditor token is both 403'd at the API layer AND would see
zero rows at the DB layer.
"""
from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.database import get_session
from app.models import (
    AnalyticsOutput,
    AuditLedger,
    AuditorPerformance,
    CrossReferenceFinding,
    Document,
    DocumentCertification,
    RiskAlert,
    User,
    WasteMapItem,
)
from app.models.enums import FileType, OutputType, Severity
from app.schemas.dashboard import (
    AnomalyOut,
    CategorySlice,
    CertificationBrief,
    CrossRefOut,
    DepartmentRow,
    Layer1Out,
    Layer2Out,
    Layer3Out,
    Layer4Out,
    LedgerEntryBrief,
    MetricCard,
)
from app.services import sla
from app.storage import load_decrypted

router = APIRouter(prefix="/owner/dashboard", tags=["owner-dashboard"])

OWNER_ROLES = ("owner", "gm", "admin", "appowner")

CATEGORY_LABELS = {
    "financial": "مالي",
    "operational": "تشغيلي",
    "human": "بشري",
    "opportunity": "فرص ضائعة",
}


def _trend(current: float, previous: float) -> tuple[str, float | None]:
    if previous == 0:
        return ("up" if current > 0 else "flat", None)
    pct = (current - previous) / abs(previous) * 100.0
    direction = "up" if pct > 1 else "down" if pct < -1 else "flat"
    return direction, round(pct, 1)


def _month_bounds_utc(ref_bg: datetime) -> tuple[datetime, datetime, datetime]:
    """Return (this_month_start, prev_month_start, now) in UTC for the Baghdad month."""
    start_this = ref_bg.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_end = start_this - timedelta(seconds=1)
    start_prev = prev_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (
        start_this.astimezone(timezone.utc),
        start_prev.astimezone(timezone.utc),
        ref_bg.astimezone(timezone.utc),
    )


@router.get("/layer1", response_model=Layer1Out)
async def layer1(
    user: User = Depends(require_role(*OWNER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> Layer1Out:
    cid = user.company_id
    now_bg = sla.now_baghdad()
    this_start, prev_start, _ = _month_bounds_utc(now_bg)

    # 1. Monthly waste (this month vs previous month for trend).
    waste_this = (
        await session.execute(
            select(func.coalesce(func.sum(WasteMapItem.amount_iqd), 0)).where(
                WasteMapItem.company_id == cid, WasteMapItem.created_at >= this_start
            )
        )
    ).scalar_one()
    waste_prev = (
        await session.execute(
            select(func.coalesce(func.sum(WasteMapItem.amount_iqd), 0)).where(
                WasteMapItem.company_id == cid,
                WasteMapItem.created_at >= prev_start,
                WasteMapItem.created_at < this_start,
            )
        )
    ).scalar_one()
    waste_dir, waste_pct = _trend(float(waste_this), float(waste_prev))

    # 2. Trust index — latest daily snapshot.
    trust = (
        await session.execute(
            select(AnalyticsOutput.trust_index)
            .where(
                AnalyticsOutput.company_id == cid,
                AnalyticsOutput.output_type == OutputType.daily_snapshot,
                AnalyticsOutput.trust_index.is_not(None),
            )
            .order_by(AnalyticsOutput.generated_at.desc())
            .limit(2)
        )
    ).scalars().all()
    trust_now = float(trust[0]) if trust else 0.0
    trust_prev = float(trust[1]) if len(trust) > 1 else trust_now
    trust_dir, trust_pct = _trend(trust_now, trust_prev)

    # 3. Critical open alerts.
    crit = (
        await session.execute(
            select(func.count())
            .select_from(RiskAlert)
            .where(
                RiskAlert.company_id == cid,
                RiskAlert.severity == Severity.critical,
                RiskAlert.status == "open",
            )
        )
    ).scalar_one()

    # 4. Predicted next-month cash outflow (latest prediction).
    pred = (
        await session.execute(
            select(AnalyticsOutput.data)
            .where(
                AnalyticsOutput.company_id == cid,
                AnalyticsOutput.output_type == OutputType.prediction,
            )
            .order_by(AnalyticsOutput.generated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    predicted_cash = 0.0
    if pred and isinstance(pred, dict) and pred.get("metric") == "next_month_cash_outflow":
        predicted_cash = float(pred.get("value", 0) or 0)

    # 5. Average auditor efficiency (today).
    today = now_bg.date()
    eff = (
        await session.execute(
            select(func.coalesce(func.avg(AuditorPerformance.efficiency_score), 0)).where(
                AuditorPerformance.company_id == cid,
                AuditorPerformance.perf_date == today,
            )
        )
    ).scalar_one()

    cards = [
        MetricCard(key="monthly_waste", label="إجمالي الهدر الشهري", value=round(float(waste_this), 2),
                   unit="IQD", trend=waste_dir, trend_pct=waste_pct),
        MetricCard(key="trust_index", label="مؤشر الثقة", value=round(trust_now, 1),
                   unit="%", trend=trust_dir, trend_pct=trust_pct),
        MetricCard(key="critical_alerts", label="عدد التنبيهات الحرجة", value=float(crit),
                   unit="count", trend="up" if crit > 0 else "flat", trend_pct=None),
        MetricCard(key="predicted_cash", label="الكاش المتوقع", value=round(predicted_cash, 2),
                   unit="IQD", trend="flat", trend_pct=None),
        MetricCard(key="team_efficiency", label="كفاءة فريق التدقيق", value=round(float(eff), 1),
                   unit="%", trend="flat", trend_pct=None),
    ]
    return Layer1Out(generated_at=datetime.now(timezone.utc), cards=cards)


@router.get("/layer2", response_model=Layer2Out)
async def layer2(
    user: User = Depends(require_role(*OWNER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> Layer2Out:
    cid = user.company_id

    # Department breakdown: waste sum per department.
    dept_rows = (
        await session.execute(
            select(
                WasteMapItem.department,
                func.coalesce(func.sum(WasteMapItem.amount_iqd), 0),
            )
            .where(WasteMapItem.company_id == cid)
            .group_by(WasteMapItem.department)
            .order_by(func.sum(WasteMapItem.amount_iqd).desc())
        )
    ).all()

    # Risk count per department isn't directly on risk_alerts; approximate via
    # waste items count per department (risk_alerts has no department column).
    risk_counts = dict(
        (
            await session.execute(
                select(WasteMapItem.department, func.count())
                .where(WasteMapItem.company_id == cid)
                .group_by(WasteMapItem.department)
            )
        ).all()
    )

    departments = [
        DepartmentRow(
            department=dept or "غير محدد",
            total_waste_iqd=round(float(total), 2),
            risk_count=int(risk_counts.get(dept, 0)),
        )
        for dept, total in dept_rows
    ]

    # Category breakdown.
    cat_rows = (
        await session.execute(
            select(
                WasteMapItem.category,
                func.coalesce(func.sum(WasteMapItem.amount_iqd), 0),
            )
            .where(WasteMapItem.company_id == cid)
            .group_by(WasteMapItem.category)
        )
    ).all()
    categories = [
        CategorySlice(
            category=(cat.value if hasattr(cat, "value") else str(cat)),
            label=CATEGORY_LABELS.get(cat.value if hasattr(cat, "value") else str(cat), str(cat)),
            amount_iqd=round(float(total), 2),
        )
        for cat, total in cat_rows
    ]

    return Layer2Out(departments=departments, categories=categories)


@router.get("/layer3", response_model=Layer3Out)
async def layer3(
    user: User = Depends(require_role(*OWNER_ROLES)),
    session: AsyncSession = Depends(get_session),
    department: str | None = Query(None),
    severity: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
) -> Layer3Out:
    cid = user.company_id

    # Narratives (latest few).
    narr_rows = (
        await session.execute(
            select(AnalyticsOutput.data, AnalyticsOutput.generated_at)
            .where(
                AnalyticsOutput.company_id == cid,
                AnalyticsOutput.output_type == OutputType.narrative,
            )
            .order_by(AnalyticsOutput.generated_at.desc())
            .limit(10)
        )
    ).all()
    narratives = [
        {**(d if isinstance(d, dict) else {}), "generated_at": ts.isoformat()}
        for d, ts in narr_rows
    ]

    # Cross-reference findings.
    xq = select(CrossReferenceFinding).where(CrossReferenceFinding.company_id == cid)
    if severity:
        xq = xq.where(CrossReferenceFinding.severity == severity)
    if date_from:
        xq = xq.where(CrossReferenceFinding.created_at >= date_from)
    if date_to:
        xq = xq.where(CrossReferenceFinding.created_at <= date_to)
    xq = xq.order_by(CrossReferenceFinding.created_at.desc()).limit(200)
    xrows = (await session.execute(xq)).scalars().all()
    cross_refs = [
        CrossRefOut(
            id=x.id,
            finding_type=x.finding_type,
            description=x.description,
            variance_amount=float(x.variance_amount) if x.variance_amount is not None else None,
            variance_pct=float(x.variance_pct) if x.variance_pct is not None else None,
            severity=x.severity,
            status=x.status,
            created_at=x.created_at,
        )
        for x in xrows
    ]

    # Anomalies (risk_alerts).
    aq = select(RiskAlert).where(RiskAlert.company_id == cid)
    if severity:
        try:
            aq = aq.where(RiskAlert.severity == Severity(severity))
        except ValueError:
            pass
    if date_from:
        aq = aq.where(RiskAlert.created_at >= date_from)
    if date_to:
        aq = aq.where(RiskAlert.created_at <= date_to)
    aq = aq.order_by(RiskAlert.created_at.desc()).limit(200)
    arows = (await session.execute(aq)).scalars().all()
    anomalies = [
        AnomalyOut(
            id=a.id,
            severity=a.severity.value if hasattr(a.severity, "value") else str(a.severity),
            title=a.title,
            description=a.description,
            financial_impact=float(a.financial_impact) if a.financial_impact is not None else None,
            status=a.status,
            created_at=a.created_at,
        )
        for a in arows
    ]

    return Layer3Out(
        narratives=narratives,
        cross_reference_findings=cross_refs,
        anomalies=anomalies,
    )


@router.get("/layer4/{document_id}", response_model=Layer4Out)
async def layer4(
    document_id: uuid.UUID,
    user: User = Depends(require_role(*OWNER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> Layer4Out:
    doc = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if doc is None or doc.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="المستند غير موجود")

    # Decrypt original for display.
    image_url: str | None = None
    if doc.file_type in (FileType.image, FileType.pdf):
        try:
            raw = await load_decrypted(
                relative_path=doc.file_path,
                company_id=str(doc.company_id),
                file_uuid=str(doc.id),
            )
            mime = "image/png" if doc.file_type == FileType.image else "application/pdf"
            image_url = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
            del raw
        except Exception:  # noqa: BLE001 - missing/corrupt/undecryptable file must not 500 the dashboard
            image_url = None

    # Uploader name.
    uploader_name = None
    if doc.uploaded_by:
        uploader_name = (
            await session.execute(select(User.full_name).where(User.id == doc.uploaded_by))
        ).scalar_one_or_none()

    # Certifications.
    cert_rows = (
        await session.execute(
            select(DocumentCertification)
            .where(DocumentCertification.document_id == doc.id)
            .order_by(DocumentCertification.certified_at.asc())
        )
    ).scalars().all()
    cert_names = {}
    auditor_ids = {c.auditor_id for c in cert_rows if c.auditor_id}
    if auditor_ids:
        cert_names = dict(
            (await session.execute(select(User.id, User.full_name).where(User.id.in_(auditor_ids)))).all()
        )
    certifications = [
        CertificationBrief(
            id=c.id,
            auditor_id=c.auditor_id,
            auditor_name=cert_names.get(c.auditor_id),
            is_valid=c.is_valid,
            corrections_made=c.corrections_made,
            certified_at=c.certified_at,
        )
        for c in cert_rows
    ]

    # Ledger entries referencing this document or its certifications.
    cert_ids = [c.id for c in cert_rows]
    record_ids = [doc.id, *cert_ids]
    ledger_rows = (
        await session.execute(
            select(AuditLedger)
            .where(AuditLedger.record_id.in_(record_ids))
            .order_by(AuditLedger.created_at.asc())
        )
    ).scalars().all()
    ledger_user_ids = {e.created_by for e in ledger_rows if e.created_by}
    ledger_names = {}
    if ledger_user_ids:
        ledger_names = dict(
            (await session.execute(select(User.id, User.full_name).where(User.id.in_(ledger_user_ids)))).all()
        )
    ledger_entries = [
        LedgerEntryBrief(
            id=e.id,
            action=e.action.value if hasattr(e.action, "value") else str(e.action),
            reason=e.reason,
            created_by=e.created_by,
            created_by_name=ledger_names.get(e.created_by),
            current_hash=e.current_hash,
            created_at=e.created_at,
        )
        for e in ledger_rows
    ]

    return Layer4Out(
        document_id=doc.id,
        original_filename=doc.original_filename,
        file_type=doc.file_type.value if hasattr(doc.file_type, "value") else str(doc.file_type),
        doc_category=doc.doc_category.value if hasattr(doc.doc_category, "value") else str(doc.doc_category),
        status=doc.status.value if hasattr(doc.status, "value") else str(doc.status),
        confidence_score=float(doc.confidence_score) if doc.confidence_score is not None else None,
        uploaded_by=doc.uploaded_by,
        uploaded_by_name=uploader_name,
        original_image_url=image_url,
        extracted_data=doc.extracted_data,
        certifications=certifications,
        ledger_entries=ledger_entries,
    )
