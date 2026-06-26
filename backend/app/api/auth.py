"""Auth API.

Supabase issues access/refresh tokens. We expose:
  - POST /auth/login : a server-side login PROXY that rate-limits attempts
    (5 failures → 15-min lockout per email+IP) before forwarding the password
    grant to Supabase. This lets us enforce lockout that the browser-direct
    Supabase login cannot.
  - GET  /auth/me    : resolve the public.users profile for a bearer token.

The frontend may still use the Supabase client directly; using this proxy adds
the rate-limit protection.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr

from app.api.deps import get_current_user
from app.config import settings
from app.models import User
from app.schemas.auth import UserOut
from app.services import rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])

MSG_INVALID = "البريد الإلكتروني أو كلمة المرور غير صحيحة"
MSG_LOCKED = "تم تجاوز عدد المحاولات المسموح. تم قفل الحساب مؤقتاً، حاول لاحقاً."
MSG_UNCONFIGURED = "خدمة تسجيل الدخول غير مهيأة على الخادم"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None


async def _password_grant(email: str, password: str) -> tuple[int, dict]:
    """Call Supabase's password-grant endpoint. Returns (status_code, json).

    Isolated so tests can monkeypatch it without touching the global httpx.
    """
    url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/token?grant_type=password"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            url,
            headers={"apikey": settings.SUPABASE_ANON_KEY, "Content-Type": "application/json"},
            json={"email": email, "password": password},
        )
    try:
        payload = resp.json()
    except Exception:  # noqa: BLE001
        payload = {}
    return resp.status_code, payload


def _client_ip(request: Request) -> str:
    # Honor a single proxy hop if present.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request) -> LoginResponse:
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=MSG_UNCONFIGURED)

    key = rate_limit.make_key(body.email, _client_ip(request))

    locked = await rate_limit.check_locked(key)
    if locked > 0:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=MSG_LOCKED,
            headers={"Retry-After": str(locked)},
        )

    # Forward the password grant to Supabase.
    try:
        status_code, data = await _password_grant(body.email, body.password)
    except Exception:  # noqa: BLE001 - upstream unreachable
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="تعذّر الاتصال بخدمة المصادقة")

    if status_code == 200:
        await rate_limit.clear(key)
        return LoginResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
        )

    # Failed credentials → register the attempt (and maybe lock).
    result = await rate_limit.register_failure(key)
    if result["locked"]:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=MSG_LOCKED,
            headers={"Retry-After": str(result["lock_seconds"])},
        )
    remaining = result["remaining_attempts"]
    detail = MSG_INVALID + (f" (محاولات متبقية: {remaining})" if remaining else "")
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=detail)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
