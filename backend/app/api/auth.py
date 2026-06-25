from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError
import uuid

from app.database import get_session
from app.models import User
from app.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.schemas.auth import LoginRequest, TokenPair, RefreshRequest, UserOut
from app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_CREDS_AR = "البريد الإلكتروني أو كلمة المرور غير صحيحة"
INVALID_REFRESH_AR = "رمز التحديث غير صالح أو منتهي الصلاحية"


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    user = (await session.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDS_AR)

    access = create_access_token(sub=str(user.id), role=user.role.value)
    refresh = create_refresh_token(sub=str(user.id))
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise JWTError()
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=INVALID_REFRESH_AR)

    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=INVALID_REFRESH_AR)

    return TokenPair(
        access_token=create_access_token(sub=str(user.id), role=user.role.value),
        refresh_token=create_refresh_token(sub=str(user.id)),
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
