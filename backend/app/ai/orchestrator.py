"""Orchestrator — runs the full daily AI analysis for a company.

Steps:
  1. DataQualityGuard
  2. AnomalyDetector
  3. CrossReferencer
  4. FinancialImpactCalculator
  5. Predictor
  6. NarrativeGenerator
  7. Trust Index
  8. Persist a daily snapshot into analytics_outputs

All writes target RLS-protected tables; the orchestrator binds a NON-auditor
role ('admin') on its DB session so RLS allows the inserts (and auditors still
cannot read them).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import (
    anomaly as anomaly_mod,
    cross_reference as xref_mod,
    data_quality as dq_mod,
    impact as impact_mod,
    narrative as narrative_mod,
    predictor as predictor_mod,
    trust as trust_mod,
)
from app.ai.common import records_from_documents
from app.database import AsyncSessionLocal, set_user_role
from app.models import (
    AnalyticsOutput,
    AuditTask,
    Company,
    CrossReferenceFinding,
    Document,
    RiskAlert,
    WasteMapItem,
)
from app.models.enums import (
    DocStatus,
    OutputType,
    Severity,
    TaskStatus,
    WasteCategory,
)


def _sev(value: str) -> Severity:
    try:
        return Severity(value)
    except ValueError:
        return Severity.high


def _wcat(value: str) -> WasteCategory:
    try:
        return WasteCategory(value)
    except ValueError:
        return WasteCategory.financial


async def _load_certified_docs(session: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(Document).where(
                Document.company_id == company_id,
                Document.status == DocStatus.certified,
            )
        )
    ).scalars().all()
    return [
        {
            "id": d.id,
            "doc_category": d.doc_category.value if hasattr(d.doc_category, "value") else d.doc_category,
            "branch_id": d.branch_id,
            "extracted_data": d.extracted_data,
        }
        for d in rows
    ]


async def run_analysis_for_company(company_id: uuid.UUID | str) -> dict:
    """Run the full pipeline for one company and persist results."""
    cid = uuid.UUID(str(company_id))

    async with AsyncSessionLocal() as session:
        await set_user_role(session, "admin")  # non-auditor → RLS permits writes

        company = (
            await session.execute(select(Company).where(Company.id == cid))
        ).scalar_one_or_none()
        if company is None:
            return {"ok": False, "reason": "company_not_found"}

        docs = await _load_certified_docs(session, cid)
        total_docs = (
            await session.execute(
                select(func.count()).select_from(Document).where(Document.company_id == cid)
            )
        ).scalar_one()

        records = records_from_documents(docs)
        records_by_id = {r.document_id: r for r in records}

        # Step 1: data quality
        flags = dq_mod.run_data_quality(records)
        q_score = dq_mod.quality_score(records, flags)

        # Step 2: anomalies → risk_alerts (+ classify/route alerts)
        from app.services import alert_service

        anomalies = anomaly_mod.run_anomaly_detection(records)
        for a in anomalies:
            ra = RiskAlert(
                company_id=cid,
                severity=_sev(a.severity),
                title=a.title,
                description=a.description,
                financial_impact=(
                    Decimal(str(round(a.financial_impact, 2)))
                    if a.financial_impact is not None
                    else None
                ),
                status="open",
            )
            session.add(ra)
            await session.flush()  # get ra.id
            await alert_service.handle_risk_alert(
                session,
                company_id=cid,
                severity=ra.severity.value if hasattr(ra.severity, "value") else str(ra.severity),
                department="المشتريات",
                short_desc=a.title,
                financial_impact=a.financial_impact,
                ref_id=ra.id,
            )

        # Step 3: cross-reference → cross_reference_findings
        findings = xref_mod.run_cross_reference(records)
        for f in findings:
            session.add(
                CrossReferenceFinding(
                    company_id=cid,
                    finding_type=f.finding_type,
                    description=f.description,
                    variance_amount=(
                        Decimal(str(round(f.variance_amount, 2)))
                        if f.variance_amount is not None
                        else None
                    ),
                    variance_pct=(
                        Decimal(str(f.variance_pct)) if f.variance_pct is not None else None
                    ),
                    severity=f.severity,
                    details=f.details,
                    status="open",
                )
            )

        # Step 4: financial impact → waste_map_items
        waste = impact_mod.run_impact(anomalies, findings, flags, records_by_id)
        for w in waste:
            session.add(
                WasteMapItem(
                    company_id=cid,
                    category=_wcat(w.category),
                    amount_iqd=Decimal(str(round(w.amount_iqd, 2))),
                    department=w.department,
                    description=w.description,
                    status="open",
                )
            )

        # Step 5: predictions → analytics_outputs(prediction)
        predictions = predictor_mod.run_predictions(records)
        for p in predictions:
            session.add(
                AnalyticsOutput(
                    company_id=cid,
                    output_type=OutputType.prediction,
                    data={
                        "metric": p.metric,
                        "value": p.value,
                        "method": p.method,
                        "description": p.description,
                        "details": p.details,
                    },
                )
            )

        # Step 6: narratives → analytics_outputs(narrative)
        open_corrections = (
            await session.execute(
                select(func.count())
                .select_from(AuditTask)
                .where(AuditTask.status.in_([TaskStatus.pending, TaskStatus.in_progress]))
            )
        ).scalar_one()
        narratives = narrative_mod.run_narratives(waste, findings, anomalies, open_corrections)
        for n in narratives:
            session.add(
                AnalyticsOutput(
                    company_id=cid,
                    output_type=OutputType.narrative,
                    data={"audience": n.audience, "text": n.text},
                )
            )

        # Step 7: Trust Index
        coverage = trust_mod.coverage_ratio(len(docs), total_docs)
        tindex = trust_mod.trust_index(q_score, coverage, len(anomalies), len(records))

        # Step 8: daily snapshot
        total_waste = sum(float(w.amount_iqd) for w in waste)
        snapshot = AnalyticsOutput(
            company_id=cid,
            output_type=OutputType.daily_snapshot,
            trust_index=tindex,
            data={
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "certified_docs": len(docs),
                "total_docs": total_docs,
                "quality_score": q_score,
                "coverage_ratio": round(coverage, 3),
                "trust_index": tindex,
                "counts": {
                    "quality_flags": len(flags),
                    "anomalies": len(anomalies),
                    "cross_ref_findings": len(findings),
                    "waste_items": len(waste),
                    "predictions": len(predictions),
                },
                "total_waste_iqd": round(total_waste, 2),
            },
        )
        session.add(snapshot)

        await session.commit()

        return {
            "ok": True,
            "company_id": str(cid),
            "certified_docs": len(docs),
            "quality_score": q_score,
            "anomalies": len(anomalies),
            "cross_ref_findings": len(findings),
            "waste_items": len(waste),
            "predictions": len(predictions),
            "narratives": len(narratives),
            "trust_index": tindex,
            "total_waste_iqd": round(total_waste, 2),
        }


async def run_analysis_all_companies() -> dict:
    """Run analysis for every company (used by the 02:00 beat job)."""
    async with AsyncSessionLocal() as session:
        await set_user_role(session, "admin")
        company_ids = (await session.execute(select(Company.id))).scalars().all()

    results = []
    for cid in company_ids:
        results.append(await run_analysis_for_company(cid))
    return {"companies": len(company_ids), "results": results}
