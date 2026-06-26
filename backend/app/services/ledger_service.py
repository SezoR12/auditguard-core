"""Tamper-proof audit ledger service (SHA-256 hash chain).

Canonical hashing (per spec):
    current_hash = SHA-256(
        previous_hash + json.dumps(
            {table_name, record_id, action, old_value, new_value,
             reason, created_by, created_at},
            sort_keys=True
        )
    )

`created_at` is set explicitly in Python at append time (UTC, tz-aware) and
stored, so the chain is fully re-verifiable from the database alone.

The ledger is APPEND-ONLY at the application level: this module never updates
or deletes entries, and no API exposes update/delete.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
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


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=_json_default)


def compute_entry_hash(
    *,
    previous_hash: str,
    table_name: str,
    record_id: Any,
    action: str,
    old_value: dict | None,
    new_value: dict | None,
    reason: str | None,
    created_by: Any,
    created_at: datetime,
) -> str:
    """Deterministically compute an entry's current_hash, chained to previous."""
    payload = {
        "table_name": table_name,
        "record_id": str(record_id),
        "action": action,
        "old_value": old_value,
        "new_value": new_value,
        "reason": reason,
        "created_by": str(created_by) if created_by is not None else None,
        "created_at": created_at.isoformat(),
    }
    return hashlib.sha256((previous_hash + _canonical(payload)).encode("utf-8")).hexdigest()


async def get_last_hash(session: AsyncSession) -> str:
    """Most recent entry's current_hash (by created_at, id), or GENESIS_HASH."""
    row = (
        await session.execute(
            select(AuditLedger.current_hash)
            .order_by(AuditLedger.created_at.desc(), AuditLedger.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row or GENESIS_HASH


async def append_ledger_entry(
    session: AsyncSession,
    *,
    table_name: str,
    record_id: uuid.UUID,
    action: LedgerAction | str,
    created_by: uuid.UUID | None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    reason: str | None = None,
) -> AuditLedger:
    """Append a hash-chained ledger entry (added to the session, not committed)."""
    previous_hash = await get_last_hash(session)
    action_str = action.value if hasattr(action, "value") else str(action)
    created_at = datetime.now(timezone.utc)

    current_hash = compute_entry_hash(
        previous_hash=previous_hash,
        table_name=table_name,
        record_id=record_id,
        action=action_str,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        created_by=created_by,
        created_at=created_at,
    )

    entry = AuditLedger(
        table_name=table_name,
        record_id=record_id,
        action=action if isinstance(action, LedgerAction) else LedgerAction(action_str),
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        created_by=created_by,
        previous_hash=previous_hash,
        current_hash=current_hash,
        created_at=created_at,
    )
    session.add(entry)
    return entry


@dataclass
class IntegrityResult:
    is_valid: bool
    total_entries: int
    broken_links: list[str]
    last_verified_at: datetime

    def as_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "total_entries": self.total_entries,
            "broken_links": self.broken_links,
            "last_verified_at": self.last_verified_at.isoformat(),
        }


async def verify_ledger_integrity(session: AsyncSession) -> IntegrityResult:
    """Re-walk the whole chain and report any broken links.

    For each entry (ordered by created_at, id):
      - recompute current_hash and compare with stored value
      - confirm previous_hash equals the prior entry's current_hash
    Returns the IDs of any entries that fail.
    """
    entries = (
        await session.execute(
            select(AuditLedger).order_by(AuditLedger.created_at.asc(), AuditLedger.id.asc())
        )
    ).scalars().all()

    broken: list[str] = []
    prev = GENESIS_HASH
    for e in entries:
        action_str = e.action.value if hasattr(e.action, "value") else str(e.action)
        created_at = e.created_at
        if created_at is not None and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        expected = compute_entry_hash(
            previous_hash=prev,
            table_name=e.table_name,
            record_id=e.record_id,
            action=action_str,
            old_value=e.old_value,
            new_value=e.new_value,
            reason=e.reason,
            created_by=e.created_by,
            created_at=created_at,
        )
        if e.previous_hash != prev or e.current_hash != expected:
            broken.append(str(e.id))
        prev = e.current_hash

    return IntegrityResult(
        is_valid=len(broken) == 0,
        total_entries=len(entries),
        broken_links=broken,
        last_verified_at=datetime.now(timezone.utc),
    )


# --- Tamper-proof certificate (for report exports, Phase 9) ------------------


def build_tamper_proof_certificate(
    *,
    report_id: str,
    report_content: str | bytes,
    ledger_hash_at_generation: str,
    company_key: str,
) -> dict:
    """Build a certificate binding a report to the ledger state + an HMAC sig."""
    import hmac

    if isinstance(report_content, str):
        report_content = report_content.encode("utf-8")
    generated_at = datetime.now(timezone.utc)
    signature = hmac.new(
        company_key.encode("utf-8"),
        report_content + report_id.encode("utf-8") + ledger_hash_at_generation.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "report_id": report_id,
        "generated_at": generated_at.isoformat(),
        "ledger_hash_at_generation": ledger_hash_at_generation,
        "digital_signature": signature,
        "algorithm": "HMAC-SHA256",
    }
