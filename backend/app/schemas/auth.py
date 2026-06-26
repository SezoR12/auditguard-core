from pydantic import BaseModel, EmailStr
import uuid


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: str
    company_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    is_active: bool

    class Config:
        from_attributes = True
