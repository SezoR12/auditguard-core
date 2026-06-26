"""No-Code report templates + CRaaS fulfilment models.

- ReportTemplate: a JSON template authored by the App Owner (sector-aware).
- ReportRequest: a client's CRaaS request ("طلب تقرير تحليلي مخصص").
- CustomReport: a template deployed into a specific company's library.
- ConsolidatedEntity / ConsolidatedMetric: Elite-tier multi-box federation
  schema (architecture only; not populated in the MVP).
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class ReportTemplate(Base):
    __tablename__ = "report_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sectors this template targets (criteria modules), e.g. ["real_estate"].
    sectors: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # The no-code canvas config: blocks (table/chart/text/image) + data bindings.
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Authoring/versioning.
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReportRequest(Base):
    __tablename__ = "report_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    # requested | designing | priced | deployed | rejected
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="requested")
    price_iqd: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CustomReport(Base):
    """A template deployed into a company's 'Custom Reports' library."""

    __tablename__ = "custom_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Snapshot of the template config at deploy time (so client renders are stable).
    config_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Elite-tier multi-company federation (schema only, MVP not implemented) --


class ConsolidatedEntity(Base):
    """A Smart Box / subsidiary that reports up to a conglomerate parent."""

    __tablename__ = "consolidated_entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    entity_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Remote box identity / federation endpoint (no secrets stored here).
    box_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConsolidatedMetric(Base):
    """Periodically federated aggregate metrics from each entity (architecture)."""

    __tablename__ = "consolidated_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consolidated_entities.id", ondelete="CASCADE"), nullable=False
    )
    metric_key: Mapped[str] = mapped_column(String(80), nullable=False)
    metric_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    period: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. 2026-06
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    federated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
