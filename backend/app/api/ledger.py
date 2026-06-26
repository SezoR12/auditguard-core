"""Owner-only ledger query + integrity verification API.

The ledger is append-only: this module exposes ONLY read/verify endpoints.
There is intentionally no update or delete endpoint anywhere in the app.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.database import get_session
from app.models import AuditLedger, User
from app.schemas.ledger import LedgerEntryOut, LedgerPage, LedgerVerifyOut
from app.services.ledger_service import (
    GENESIS_HASH,
    compute_entry_hash,
    verify_ledger_integrity,
)

router = APIRouter(prefix="/owner/ledger", tags=["ledger"])


def _entry_valid(entry: AuditLedger, prev_hash: str) -> bool:
    action_str = entry.action.value if hasattr(entry.action, "value") else str(entry.action)
    created_at = entry.created_at
    if created_at is not None and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    expected = compute_entry_hash(
        previous_hash=prev_hash,
        table_name=entry.table_name,
        record_id=entry.record_id,
        action=action_str,
        old_value=entry.old_value,
        new_value=entry.new_value,
        reason=entry.reason,
        created_by=entry.created_by,
        created_at=created_at,
    )
    return entry.previous_hash == prev_hash and entry.current_hash == expected


@router.get("", response_model=LedgerPage)
async def list_ledger(
    user: User = Depends(require_role("owner", "gm", "admin", "appowner")),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    table_name: str | None = Query(None),
    user_id: uuid.UUID | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
) -> LedgerPage:
    """Paginated, filterable ledger view with per-entry chain_status.

    chain_status is computed by walking the chain from genesis up to each entry
    (so the validity reflects the true chain, not just the visible page).
    """
    # Build the filtered query.
    conditions = []
    if table_name:
        conditions.append(AuditLedger.table_name == table_name)
    if user_id:
        conditions.append(AuditLedger.created_by == user_id)
    if date_from:
        conditions.append(AuditLedger.created_at >= date_from)
    if date_to:
        conditions.append(AuditLedger.created_at <= date_to)

    total = (
        await session.execute(
            select(func.count()).select_from(AuditLedger).where(*conditions)
        )
    ).scalar_one()

    # We need full-chain validity, so compute hashes walking from the start.
    # Load all entries in order, track running prev_hash + validity per id.
    all_entries = (
        await session.execute(
            select(AuditLedger).order_by(
                AuditLedger.created_at.asc(), AuditLedger.id.asc()
            )
        )
    ).scalars().all()

    validity: dict[uuid.UUID, str] = {}
    prev = GENESIS_HASH
    for e in all_entries:
        validity[e.id] = "valid" if _entry_valid(e, prev) else "invalid"
        prev = e.current_hash

    # User name lookup.
    user_ids = {e.created_by for e in all_entries if e.created_by}
    names: dict[uuid.UUID, str] = {}
    if user_ids:
        rows = (
            await session.execute(
                select(User.id, User.full_name).where(User.id.in_(user_ids))
            )
        ).all()
        names = {uid: name for uid, name in rows}

    # Apply filters + pagination in Python over the ordered list (newest first).
    def _match(e: AuditLedger) -> bool:
        if table_name and e.table_name != table_name:
            return False
        if user_id and e.created_by != user_id:
            return False
        ca = e.created_at
        if ca is not None and ca.tzinfo is None:
            ca = ca.replace(tzinfo=timezone.utc)
        if date_from and (ca is None or ca < date_from):
            return False
        if date_to and (ca is None or ca > date_to):
            return False
        return True

    filtered = [e for e in reversed(all_entries) if _match(e)]
    page = filtered[offset : offset + limit]

    entries = [
        LedgerEntryOut(
            id=e.id,
            created_at=e.created_at,
            created_by=e.created_by,
            created_by_name=names.get(e.created_by),
            table_name=e.table_name,
            record_id=e.record_id,
            action=e.action.value if hasattr(e.action, "value") else str(e.action),
            reason=e.reason,
            previous_hash=e.previous_hash,
            current_hash=e.current_hash,
            chain_status=validity.get(e.id, "valid"),
        )
        for e in page
    ]
    return LedgerPage(total=total, limit=limit, offset=offset, entries=entries)


@router.get("/verify", response_model=LedgerVerifyOut)
async def verify_ledger(
    user: User = Depends(require_role("owner", "gm", "admin", "appowner")),
    session: AsyncSession = Depends(get_session),
) -> LedgerVerifyOut:
    """Run full chain verification and report any broken links."""
    result = await verify_ledger_integrity(session)
    return LedgerVerifyOut(**result.as_dict())
