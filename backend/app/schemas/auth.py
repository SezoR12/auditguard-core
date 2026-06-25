from pydantic import BaseModel, EmailStr
import uuid


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


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
