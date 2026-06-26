"""Server-side token denylist (Redis) for hard revocation.

Two revocation modes:
  1. Per-token: deny a single access token until its own `exp` (keyed by a hash
     of the token, so the entry self-expires when the token would have).
  2. Per-user: a "revoke before" timestamp for a Supabase user (`sub`); any
     token issued (`iat`) at/under that time is rejected. Useful to log a user
     out of ALL sessions (e.g. after password reset / suspected compromise).

Checked in get_current_user on every request. Fails OPEN if Redis is down
(availability over hard-revocation) — tune if you need fail-closed.
"""
from __future__ import annotations

import hashlib
import time

import redis.asyncio as aioredis

from app.config import settings

_TOKEN_PREFIX = "denylist:token:"
_USER_PREFIX = "denylist:user:"  # value = unix ts; tokens with iat <= ts denied


def _redis() -> aioredis.Redis:
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


def _token_key(token: str) -> str:
    return _TOKEN_PREFIX + hashlib.sha256(token.encode("utf-8")).hexdigest()


async def deny_token(token: str, exp: int | None) -> None:
    """Deny a single token until `exp` (unix seconds). No-op if already expired."""
    ttl = max(1, int(exp) - int(time.time())) if exp else 3600
    r = _redis()
    try:
        await r.set(_token_key(token), "1", ex=ttl)
    finally:
        await r.aclose()


async def revoke_user(sub: str, *, before: int | None = None, horizon: int = 7 * 24 * 3600) -> None:
    """Revoke all of a user's tokens issued at/before `before` (default: now)."""
    ts = int(before if before is not None else time.time())
    r = _redis()
    try:
        await r.set(_USER_PREFIX + str(sub), str(ts), ex=horizon)
    finally:
        await r.aclose()


async def is_denied(token: str, *, sub: str | None = None, iat: int | None = None) -> bool:
    """True if the token is individually denied or covered by a user revocation."""
    r = _redis()
    try:
        if await r.exists(_token_key(token)):
            return True
        if sub is not None:
            cutoff = await r.get(_USER_PREFIX + str(sub))
            if cutoff is not None and iat is not None and int(iat) <= int(cutoff):
                return True
        return False
    except Exception:  # noqa: BLE001 - Redis down -> fail open (don't lock everyone out)
        return False
    finally:
        try:
            await r.aclose()
        except Exception:  # noqa: BLE001
            pass
