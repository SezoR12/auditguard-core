"""Schemas for the Owner 4-layer dashboard."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


# --- Layer 1: executive metrics ---------------------------------------------
class MetricCard(BaseModel):
    key: str
    label: str  # Arabic
    value: float
    unit: str  # "IQD" | "%" | "count" | ""
    trend: str  # "up" | "down" | "flat"
    trend_pct: float | None = None


class Layer1Out(BaseModel):
    generated_at: datetime
    cards: list[MetricCard]


# --- Layer 2: department breakdown ------------------------------------------
class DepartmentRow(BaseModel):
    department: str
    total_waste_iqd: float
    risk_count: int


class CategorySlice(BaseModel):
    category: str  # financial / operational / human / opportunity
    label: str  # Arabic
    amount_iqd: float


class Layer2Out(BaseModel):
    departments: list[DepartmentRow]
    categories: list[CategorySlice]


# --- Layer 3: AI findings ----------------------------------------------------
class CrossRefOut(BaseModel):
    id: uuid.UUID
    finding_type: str
    description: str
    variance_amount: float | None = None
    variance_pct: float | None = None
    severity: str
    status: str
    created_at: datetime


class AnomalyOut(BaseModel):
    id: uuid.UUID
    severity: str
    title: str
    description: str
    financial_impact: float | None = None
    status: str
    created_at: datetime


class Layer3Out(BaseModel):
    narratives: list[dict[str, Any]]
    cross_reference_findings: list[CrossRefOut]
    anomalies: list[AnomalyOut]


# --- Layer 4: raw data -------------------------------------------------------
class LedgerEntryBrief(BaseModel):
    id: uuid.UUID
    action: str
    reason: str | None = None
    created_by: uuid.UUID | None = None
    created_by_name: str | None = None
    current_hash: str
    created_at: datetime


class CertificationBrief(BaseModel):
    id: uuid.UUID
    auditor_id: uuid.UUID
    auditor_name: str | None = None
    is_valid: bool
    corrections_made: dict | None = None
    certified_at: datetime


class Layer4Out(BaseModel):
    document_id: uuid.UUID
    original_filename: str
    file_type: str
    doc_category: str
    status: str
    confidence_score: float | None = None
    uploaded_by: uuid.UUID | None = None
    uploaded_by_name: str | None = None
    original_image_url: str | None = None
    extracted_data: dict | None = None
    certifications: list[CertificationBrief]
    ledger_entries: list[LedgerEntryBrief]
