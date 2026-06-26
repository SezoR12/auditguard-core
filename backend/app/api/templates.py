"""Template Builder + CRaaS API.

App Owner (appowner/admin):
  - GET  /templates/criteria              criteria library catalog
  - CRUD /templates                       author/save report templates (JSON)
  - POST /templates/{id}/preview          render with dummy data
  - GET  /admin/report-requests           inbox of client CRaaS requests
  - POST /admin/report-requests/{id}/deploy  price + deploy template to client

Client (owner/gm):
  - POST /owner/report-requests           "طلب تقرير تحليلي مخصص"
  - GET  /owner/report-requests           own requests
  - GET  /owner/custom-reports            deployed reports library
  - POST /owner/custom-reports/{id}/generate  render PDF with live data
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.database import get_session
from app.models import CustomReport, ReportRequest, ReportTemplate, User
from app.services import criteria_library
from app.services.template_engine import DUMMY, render_pdf, resolve_data

router = APIRouter(tags=["templates"])

APPOWNER_ROLES = ("appowner", "admin")
CLIENT_ROLES = ("owner", "gm", "admin", "appowner")


# --- schemas ----------------------------------------------------------------
class TemplateIn(BaseModel):
    name: str
    description: str | None = None
    sectors: list[str] | None = None
    config: dict
    is_published: bool = False


class TemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    sectors: list[str] | None = None
    config: dict
    version: int
    is_published: bool
    created_at: datetime


class RequestIn(BaseModel):
    title: str
    requirements: str | None = None


class DeployIn(BaseModel):
    template_id: uuid.UUID
    price_iqd: float | None = None
    report_name: str | None = None


# --- App Owner: criteria + template CRUD ------------------------------------
@router.get("/templates/criteria")
async def criteria(user: User = Depends(require_role(*APPOWNER_ROLES))) -> dict:
    return {"modules": criteria_library.list_modules()}


@router.get("/templates", response_model=list[TemplateOut])
async def list_templates(
    user: User = Depends(require_role(*APPOWNER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> list[ReportTemplate]:
    rows = (
        await session.execute(select(ReportTemplate).order_by(ReportTemplate.updated_at.desc()))
    ).scalars().all()
    return list(rows)


@router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: TemplateIn,
    user: User = Depends(require_role(*APPOWNER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> ReportTemplate:
    tpl = ReportTemplate(
        name=body.name, description=body.description, sectors=body.sectors,
        config=body.config, is_published=body.is_published, created_by=user.id,
    )
    session.add(tpl)
    await session.commit()
    await session.refresh(tpl)
    return tpl


@router.put("/templates/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: uuid.UUID,
    body: TemplateIn,
    user: User = Depends(require_role(*APPOWNER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> ReportTemplate:
    tpl = (await session.execute(select(ReportTemplate).where(ReportTemplate.id == template_id))).scalar_one_or_none()
    if tpl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="القالب غير موجود")
    tpl.name = body.name
    tpl.description = body.description
    tpl.sectors = body.sectors
    tpl.config = body.config
    tpl.is_published = body.is_published
    tpl.version += 1
    await session.commit()
    await session.refresh(tpl)
    return tpl


@router.post("/templates/{template_id}/preview")
async def preview_template(
    template_id: uuid.UUID,
    user: User = Depends(require_role(*APPOWNER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> Response:
    tpl = (await session.execute(select(ReportTemplate).where(ReportTemplate.id == template_id))).scalar_one_or_none()
    if tpl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="القالب غير موجود")
    pdf = render_pdf(tpl.config, DUMMY, title=tpl.name)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="preview.pdf"'})


# --- App Owner: CRaaS inbox + deploy ----------------------------------------
@router.get("/admin/report-requests")
async def admin_list_requests(
    user: User = Depends(require_role(*APPOWNER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = (
        await session.execute(select(ReportRequest).order_by(ReportRequest.created_at.desc()))
    ).scalars().all()
    return [
        {
            "id": str(r.id), "company_id": str(r.company_id), "title": r.title,
            "requirements": r.requirements, "status": r.status,
            "price_iqd": float(r.price_iqd) if r.price_iqd is not None else None,
            "template_id": str(r.template_id) if r.template_id else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/admin/report-requests/{request_id}/deploy")
async def deploy_template(
    request_id: uuid.UUID,
    body: DeployIn,
    user: User = Depends(require_role(*APPOWNER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    req = (await session.execute(select(ReportRequest).where(ReportRequest.id == request_id))).scalar_one_or_none()
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="الطلب غير موجود")
    tpl = (await session.execute(select(ReportTemplate).where(ReportTemplate.id == body.template_id))).scalar_one_or_none()
    if tpl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="القالب غير موجود")

    # Deploy a config snapshot into the client's company library.
    cr = CustomReport(
        company_id=req.company_id,
        template_id=tpl.id,
        name=body.report_name or tpl.name,
        config_snapshot=tpl.config,
    )
    session.add(cr)
    req.status = "deployed"
    req.template_id = tpl.id
    if body.price_iqd is not None:
        from decimal import Decimal

        req.price_iqd = Decimal(str(body.price_iqd))
    await session.commit()
    await session.refresh(cr)
    return {"deployed": True, "custom_report_id": str(cr.id), "company_id": str(req.company_id)}


# --- Client: request + library + generate -----------------------------------
@router.post("/owner/report-requests", status_code=status.HTTP_201_CREATED)
async def create_request(
    body: RequestIn,
    user: User = Depends(require_role("owner", "gm")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    req = ReportRequest(
        company_id=user.company_id, requested_by=user.id,
        title=body.title, requirements=body.requirements, status="requested",
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return {"id": str(req.id), "status": req.status}


@router.get("/owner/report-requests")
async def my_requests(
    user: User = Depends(require_role(*CLIENT_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = (
        await session.execute(
            select(ReportRequest).where(ReportRequest.company_id == user.company_id)
            .order_by(ReportRequest.created_at.desc())
        )
    ).scalars().all()
    return [
        {"id": str(r.id), "title": r.title, "status": r.status,
         "price_iqd": float(r.price_iqd) if r.price_iqd is not None else None,
         "created_at": r.created_at.isoformat()}
        for r in rows
    ]


@router.get("/owner/custom-reports")
async def custom_reports(
    user: User = Depends(require_role(*CLIENT_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = (
        await session.execute(
            select(CustomReport).where(
                CustomReport.company_id == user.company_id, CustomReport.is_active.is_(True)
            ).order_by(CustomReport.deployed_at.desc())
        )
    ).scalars().all()
    return [
        {"id": str(c.id), "name": c.name, "template_id": str(c.template_id),
         "deployed_at": c.deployed_at.isoformat()}
        for c in rows
    ]


@router.post("/owner/custom-reports/{report_id}/generate")
async def generate_custom_report(
    report_id: uuid.UUID,
    user: User = Depends(require_role(*CLIENT_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> Response:
    cr = (await session.execute(select(CustomReport).where(CustomReport.id == report_id))).scalar_one_or_none()
    if cr is None or cr.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="التقرير غير موجود")
    tpl = (await session.execute(select(ReportTemplate).where(ReportTemplate.id == cr.template_id))).scalar_one_or_none()
    sectors = (tpl.sectors if tpl else None) or []
    data = await resolve_data(session, user.company_id, sectors)
    pdf = render_pdf(cr.config_snapshot, data, title=cr.name)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="custom_report_{report_id}.pdf"'})
