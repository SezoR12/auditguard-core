"""Supabase JWT verification + (legacy) password hashing.

Supabase signs access tokens with HS256 using the project's JWT secret. We
verify here; we never mint our own tokens — the frontend calls Supabase Auth
directly and forwards the access_token as a Bearer header to this API.
"""
from typing import Any
from jose import jwt, JWTError
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def verify_supabase_jwt(token: str) -> dict[str, Any]:
    """Verify a Supabase-issued access token. Raises JWTError on failure."""
    if not settings.SUPABASE_JWT_SECRET:
        raise JWTError("SUPABASE_JWT_SECRET is not configured")
    return jwt.decode(
        token,
        settings.SUPABASE_JWT_SECRET,
        algorithms=[settings.SUPABASE_JWT_ALGORITHM],
        audience=settings.SUPABASE_JWT_AUDIENCE,
        options={"verify_aud": True},
    )
