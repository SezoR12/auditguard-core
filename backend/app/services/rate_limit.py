"""Redis-backed login rate limiting / lockout.

Tracks failed login attempts per key (email+client-ip). After
LOGIN_MAX_ATTEMPTS failures the key is locked for LOGIN_LOCKOUT_MINUTES.
A successful login clears the counter.
"""
from __future__ import annotations

import hashlib

import redis.asyncio as aioredis

from app.config import settings

_FAIL_PREFIX = "login:fail:"
_LOCK_PREFIX = "login:lock:"


def _redis() -> aioredis.Redis:
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


def make_key(email: str, client_ip: str | None) -> str:
    raw = f"{(email or '').strip().lower()}|{client_ip or '?'}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


async def check_locked(key: str) -> int:
    """Return remaining lockout seconds (0 if not locked)."""
    r = _redis()
    try:
        ttl = await r.ttl(_LOCK_PREFIX + key)
        return ttl if ttl and ttl > 0 else 0
    finally:
        await r.aclose()


async def register_failure(key: str) -> dict:
    """Record a failed attempt; lock the key when the threshold is reached.

    Returns {attempts, locked, lock_seconds, remaining_attempts}.
    """
    r = _redis()
    try:
        fail_key = _FAIL_PREFIX + key
        attempts = await r.incr(fail_key)
        if attempts == 1:
            # Start the counting window = the lockout window.
            await r.expire(fail_key, settings.LOGIN_LOCKOUT_MINUTES * 60)
        if attempts >= settings.LOGIN_MAX_ATTEMPTS:
            lock_seconds = settings.LOGIN_LOCKOUT_MINUTES * 60
            await r.set(_LOCK_PREFIX + key, "1", ex=lock_seconds)
            await r.delete(fail_key)
            return {"attempts": attempts, "locked": True, "lock_seconds": lock_seconds,
                    "remaining_attempts": 0}
        return {
            "attempts": attempts,
            "locked": False,
            "lock_seconds": 0,
            "remaining_attempts": max(0, settings.LOGIN_MAX_ATTEMPTS - attempts),
        }
    finally:
        await r.aclose()


async def clear(key: str) -> None:
    """Clear failure counter + lock (on successful login)."""
    r = _redis()
    try:
        await r.delete(_FAIL_PREFIX + key, _LOCK_PREFIX + key)
    finally:
        await r.aclose()
