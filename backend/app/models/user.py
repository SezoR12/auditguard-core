import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base
from app.models.enums import UserRole


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # Nullable: Supabase Auth owns credentials. Kept for legacy/local fallback.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # FK to auth.users(id) in the Supabase project — set by the seed/admin script.
    auth_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True, nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole, name="user_role"), nullable=False)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # WhatsApp number in E.164-ish form (e.g. 9647701234567) for alerts.
    whatsapp_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
