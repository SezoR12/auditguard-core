"""Export + What-If simulator API (owner/management only)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core_tokens import make_download_token, verify_download_token
from app.database import get_session
from app.models import User, WasteMapItem
from app.services import export_service
from app.services.whatif import WhatIfInputs, simulate

router = APIRouter(prefix="/owner", tags=["exports"])

OWNER_ROLES = ("owner", "gm", "admin", "appowner")


class ExportRequest(BaseModel):
    output_type: str = "waste_map"   # waste_map | risk_alerts | analytics
    format: str = "excel"            # excel | pdf | png
    date_from: datetime | None = None
    date_to: datetime | None = None


class ExportResponse(BaseModel):
    download_url: str
    filename: str
    expires_at: datetime


@router.post("/exports", response_model=ExportResponse)
async def create_export(
    body: ExportRequest,
    user: User = Depends(require_role(*OWNER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> ExportResponse:
    try:
        filename, content, _mime = await export_service.export_report(
            session,
            report_type=body.output_type,
            fmt=body.format,
            company_id=user.company_id,
            date_from=body.date_from,
            date_to=body.date_to,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))

    rel_path = export_service.save_export(filename, content)
    # Temporary signed token (15 min) bound to this company + file.
    token = make_download_token(rel_path, str(user.company_id), ttl_seconds=900)
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    return ExportResponse(
        download_url=f"/owner/exports/download?token={token}",
        filename=filename,
        expires_at=expires,
    )


@router.get("/exports/download")
async def download_export(token: str = Query(...)) -> Response:
    """Download a previously generated export using a short-lived signed token.

    No role dep here: the signed token itself authorizes access (valid 15 min).
    """
    payload = verify_download_token(token)
    if payload is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="رابط التنزيل غير صالح أو منتهي")
    rel_path = payload["path"]
    import os

    abs_path = os.path.join(export_service.settings.STORAGE_ROOT, rel_path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="الملف غير موجود")
    with open(abs_path, "rb") as f:
        data = f.read()
    ext = rel_path.rsplit(".", 1)[-1].lower()
    mime = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
        "png": "image/png",
    }.get(ext, "application/octet-stream")
    filename = os.path.basename(rel_path)
    return Response(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- What-If simulator ------------------------------------------------------


class WhatIfRequest(BaseModel):
    waste_item_id: uuid.UUID | None = None
    base_amount_iqd: float | None = None
    recovery_pct: float = 50.0
    implementation_months: int = 3
    implementation_cost_iqd: float = 0.0
    horizon_months: int = 6


@router.post("/what-if")
async def what_if(
    body: WhatIfRequest,
    user: User = Depends(require_role(*OWNER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    base = body.base_amount_iqd
    if body.waste_item_id is not None:
        item = (
            await session.execute(
                select(WasteMapItem).where(WasteMapItem.id == body.waste_item_id)
            )
        ).scalar_one_or_none()
        if item is None or item.company_id != user.company_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="عنصر الهدر غير موجود")
        base = float(item.amount_iqd)
    if base is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="يجب تحديد المبلغ أو عنصر الهدر")

    result = simulate(
        WhatIfInputs(
            base_amount_iqd=base,
            recovery_pct=body.recovery_pct,
            implementation_months=body.implementation_months,
            implementation_cost_iqd=body.implementation_cost_iqd,
            horizon_months=body.horizon_months,
        )
    )
    return {"inputs": body.model_dump(mode="json"), **result.as_dict()}
