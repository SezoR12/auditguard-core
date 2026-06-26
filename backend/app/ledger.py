"""Tamper-evident audit ledger helpers (SHA-256 hash chain).

Each entry's current_hash = SHA256(previous_hash + canonical(persisted columns)).
The hash covers ONLY columns stored in the row (table_name, record_id, action,
old_value, new_value, created_by), so the chain is fully verifiable later from
the database alone.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLedger
from app.models.enums import LedgerAction

GENESIS_HASH = "0" * 64


def _json_default(o: Any) -> Any:
    if isinstance(o, uuid.UUID):
        return str(o)
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


def compute_hash(
    *,
    previous_hash: str,
    table_name: str,
    record_id: str,
    action: str,
    new_value: dict | None,
    old_value: dict | None,
    created_by: str | None,
) -> str:
    """Deterministically hash a ledger entry's persisted columns, chained."""
    payload = {
        "table_name": table_name,
        "record_id": str(record_id),
        "action": action,
        "old_value": old_value,
        "new_value": new_value,
        "created_by": str(created_by) if created_by else None,
    }
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, default=_json_default
    )
    return hashlib.sha256((previous_hash + canonical).encode("utf-8")).hexdigest()


async def get_last_hash(session: AsyncSession) -> str:
    """Return the most recent ledger entry's current_hash, or GENESIS_HASH."""
    row = (
        await session.execute(
            select(AuditLedger.current_hash)
            .order_by(AuditLedger.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row or GENESIS_HASH


async def append_entry(
    session: AsyncSession,
    *,
    table_name: str,
    record_id: uuid.UUID,
    action: LedgerAction,
    created_by: uuid.UUID,
    new_value: dict | None = None,
    old_value: dict | None = None,
    reason: str | None = None,
) -> AuditLedger:
    """Create and add (not commit) a hash-chained ledger entry."""
    previous_hash = await get_last_hash(session)
    action_str = action.value if hasattr(action, "value") else str(action)
    current_hash = compute_hash(
        previous_hash=previous_hash,
        table_name=table_name,
        record_id=str(record_id),
        action=action_str,
        new_value=new_value,
        old_value=old_value,
        created_by=str(created_by),
    )
    entry = AuditLedger(
        table_name=table_name,
        record_id=record_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        created_by=created_by,
        previous_hash=previous_hash,
        current_hash=current_hash,
    )
    session.add(entry)
    return entry


def verify_chain(entries: list[dict]) -> bool:
    """Verify ledger entries (ordered by created_at) form an intact chain.

    Each dict needs: previous_hash, current_hash, table_name, record_id,
    action, new_value, old_value, created_by.
    """
    prev = GENESIS_HASH
    for e in entries:
        expected = compute_hash(
            previous_hash=prev,
            table_name=e["table_name"],
            record_id=e["record_id"],
            action=e["action"],
            new_value=e.get("new_value"),
            old_value=e.get("old_value"),
            created_by=e.get("created_by"),
        )
        if e.get("previous_hash") != prev or e.get("current_hash") != expected:
            return False
        prev = e["current_hash"]
    return True
