"""Auth API — Supabase issues access/refresh tokens directly to the frontend.

This router only exposes /auth/me so the SPA can resolve the public.users
profile (role, company, branch) for a given Supabase access token.
"""
from fastapi import APIRouter, Depends

from app.models import User
from app.schemas.auth import UserOut
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
