from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from app.database import get_session, set_user_role
from app.models import User
from app.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

UNAUTHORIZED_AR = "غير مصرح بالوصول - يجب تسجيل الدخول"
FORBIDDEN_AR = "ليس لديك الصلاحية للوصول إلى هذا المورد"


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=UNAUTHORIZED_AR)
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise JWTError()
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=UNAUTHORIZED_AR)

    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=UNAUTHORIZED_AR)

    # CRITICAL: apply role to the DB session for RLS
    await set_user_role(session, user.role.value)
    return user


def require_role(*allowed_roles: str):
    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=FORBIDDEN_AR)
        return user
    return _checker
