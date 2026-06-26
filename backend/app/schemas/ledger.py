"""Schemas for the ledger query + verification API."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class LedgerEntryOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    created_by: uuid.UUID | None = None
    created_by_name: str | None = None
    table_name: str
    record_id: uuid.UUID
    action: str
    reason: str | None = None
    previous_hash: str | None = None
    current_hash: str
    chain_status: str  # "valid" | "invalid"


class LedgerPage(BaseModel):
    total: int
    limit: int
    offset: int
    entries: list[LedgerEntryOut]


class LedgerVerifyOut(BaseModel):
    is_valid: bool
    total_entries: int
    broken_links: list[str]
    last_verified_at: datetime
