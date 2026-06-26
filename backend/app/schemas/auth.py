from pydantic import BaseModel
import uuid


class UserOut(BaseModel):
    id: uuid.UUID
    # Output-only: email was already validated at signup (Supabase Auth). We use
    # plain str here so resolving an existing profile never 500s on edge-case
    # domains (e.g. .local dev addresses).
    email: str
    full_name: str
    role: str
    company_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    is_active: bool

    class Config:
        from_attributes = True
