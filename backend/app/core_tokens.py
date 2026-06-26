"""Short-lived signed tokens for temporary download URLs (HMAC, no DB)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.config import settings


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def make_download_token(path: str, company_id: str, ttl_seconds: int = 900) -> str:
    payload = {"path": path, "company_id": company_id, "exp": int(time.time()) + ttl_seconds}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64e(sig)}"


def verify_download_token(token: str) -> dict[str, Any] | None:
    try:
        body, sig = token.split(".", 1)
        expected = hmac.new(
            settings.SECRET_KEY.encode("utf-8"), body.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64d(sig), expected):
            return None
        payload = json.loads(_b64d(body))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:  # noqa: BLE001
        return None
