"""Supabase JWT verification + (legacy) password hashing.

Supabase can sign access tokens two ways:
  * ES256 (asymmetric) — the current default. Tokens are verified against the
    project's public JWKS (GET {SUPABASE_URL}/auth/v1/.well-known/jwks.json),
    selecting the key by the token's `kid`.
  * HS256 (legacy shared secret) — older projects. Verified with
    SUPABASE_JWT_SECRET.

We support both: pick the path from the token header `alg`. We never mint our
own tokens — the frontend authenticates with Supabase directly and forwards the
access_token as a Bearer header.
"""
import time
from typing import Any

import httpx
from jose import jwt, JWTError
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# --- JWKS cache (for ES256/RS256 asymmetric verification) -------------------
_JWKS_CACHE: dict[str, Any] = {"keys": {}, "fetched_at": 0.0}
_JWKS_TTL = 600  # seconds


def _jwks_url() -> str:
    return f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"


def _get_jwk_for_kid(kid: str, *, force: bool = False) -> dict | None:
    now = time.time()
    fresh = (now - _JWKS_CACHE["fetched_at"]) < _JWKS_TTL
    if not force and fresh and kid in _JWKS_CACHE["keys"]:
        return _JWKS_CACHE["keys"][kid]
    # (Re)fetch JWKS.
    try:
        resp = httpx.get(_jwks_url(), timeout=10.0)
        resp.raise_for_status()
        keys = {k["kid"]: k for k in resp.json().get("keys", []) if "kid" in k}
        _JWKS_CACHE["keys"] = keys
        _JWKS_CACHE["fetched_at"] = now
        return keys.get(kid)
    except Exception:  # noqa: BLE001 - network/JSON issues
        # Fall back to whatever we had cached.
        return _JWKS_CACHE["keys"].get(kid)


def verify_supabase_jwt(token: str) -> dict[str, Any]:
    """Verify a Supabase-issued access token. Raises JWTError on failure."""
    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:  # noqa: BLE001
        raise JWTError(f"malformed token header: {exc}") from exc

    alg = header.get("alg", "")
    common = dict(
        audience=settings.SUPABASE_JWT_AUDIENCE,
        options={"verify_aud": True},
    )

    if alg.startswith(("ES", "RS")):
        kid = header.get("kid")
        if not kid:
            raise JWTError("asymmetric token missing 'kid'")
        jwk = _get_jwk_for_kid(kid)
        if jwk is None:
            # Force a refresh once in case of key rotation.
            jwk = _get_jwk_for_kid(kid, force=True)
        if jwk is None:
            raise JWTError(f"no JWKS key for kid={kid}")
        return jwt.decode(token, jwk, algorithms=[alg], **common)

    # Legacy HS256 path.
    if not settings.SUPABASE_JWT_SECRET:
        raise JWTError("SUPABASE_JWT_SECRET is not configured")
    return jwt.decode(
        token,
        settings.SUPABASE_JWT_SECRET,
        algorithms=[settings.SUPABASE_JWT_ALGORITHM or "HS256"],
        **common,
    )
