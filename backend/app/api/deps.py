"""Auth dependencies — validate Supabase JWTs and apply RLS role on the session."""
import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_session, set_user_context, set_user_role
from app.models import User
from app.security import verify_supabase_jwt

# tokenUrl is informational; tokens are issued by Supabase, not by this API.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="supabase-auth", auto_error=False)

UNAUTHORIZED_AR = "غير مصرح بالوصول - يجب تسجيل الدخول"
NO_PROFILE_AR = "لا يوجد ملف مستخدم مرتبط بهذا الحساب"
FORBIDDEN_AR = "ليس لديك الصلاحية للوصول إلى هذا المورد"


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=UNAUTHORIZED_AR)
    try:
        payload = verify_supabase_jwt(token)
        auth_user_id = uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=UNAUTHORIZED_AR)

    # Hard revocation: reject denied / revoked tokens (server-side denylist).
    from app.services import token_denylist

    if await token_denylist.is_denied(
        token, sub=payload.get("sub"), iat=payload.get("iat")
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=UNAUTHORIZED_AR)

    # Bootstrap RLS context with the JWT identity BEFORE the profile lookup, so
    # the users SELECT policy lets a user read (and self-link) their own row.
    await set_user_context(
        session,
        auth_user_id=str(auth_user_id),
        auth_email=payload.get("email") or None,
    )

    user = (
        await session.execute(select(User).where(User.auth_user_id == auth_user_id))
    ).scalar_one_or_none()

    # Fallback: match by email claim (e.g. profile created before linking).
    if not user:
        email = payload.get("email")
        if email:
            user = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if user and user.auth_user_id is None:
                user.auth_user_id = auth_user_id
                await session.commit()

    if not user or not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NO_PROFILE_AR)

    # CRITICAL: drive RLS off the RESOLVED profile (role + id + company/branch),
    # not the Supabase JWT claims. This scopes users/audit_tasks row visibility.
    await set_user_context(
        session,
        role=user.role.value,
        user_id=str(user.id),
        company_id=str(user.company_id) if user.company_id else None,
        branch_id=str(user.branch_id) if user.branch_id else None,
        auth_user_id=str(auth_user_id),
        auth_email=payload.get("email") or None,
    )
    return user


def require_role(*allowed_roles: str):
    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=FORBIDDEN_AR)
        return user
    return _checker
