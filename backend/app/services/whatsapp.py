"""WhatsApp dispatch via the Baileys bridge, with a Redis queue fallback.

send_whatsapp() tries the bridge; on any failure it pushes the message onto a
Redis list (settings.WHATSAPP_QUEUE_KEY) for later retry by the Celery task
notify.flush_whatsapp_queue (every 5 minutes).
"""
from __future__ import annotations

import json

import httpx
import redis.asyncio as aioredis

from app.config import settings


def _redis() -> aioredis.Redis:
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def _post_to_bridge(to: str, message: str, timeout: float = 8.0) -> bool:
    url = f"{settings.BAILEYS_URL.rstrip('/')}/send-message"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json={"to": to, "message": message})
        resp.raise_for_status()
        data = resp.json()
        return bool(data.get("ok", True))


async def enqueue(to: str, message: str) -> None:
    r = _redis()
    try:
        await r.rpush(settings.WHATSAPP_QUEUE_KEY, json.dumps({"to": to, "message": message}))
    finally:
        await r.aclose()


async def send_whatsapp(to: str | None, message: str) -> dict:
    """Send (or queue) a WhatsApp message. Returns {sent: bool, queued: bool}."""
    if not to:
        return {"sent": False, "queued": False, "reason": "no_recipient"}
    try:
        ok = await _post_to_bridge(to, message)
        if ok:
            return {"sent": True, "queued": False}
        await enqueue(to, message)
        return {"sent": False, "queued": True, "reason": "bridge_not_ok"}
    except Exception:  # noqa: BLE001 - bridge offline / network down
        await enqueue(to, message)
        return {"sent": False, "queued": True, "reason": "bridge_unreachable"}


async def flush_queue(max_items: int = 100) -> dict:
    """Drain the Redis queue, re-attempting delivery. Re-queues on failure."""
    r = _redis()
    sent = 0
    requeued = 0
    try:
        for _ in range(max_items):
            raw = await r.lpop(settings.WHATSAPP_QUEUE_KEY)
            if raw is None:
                break
            item = json.loads(raw)
            try:
                ok = await _post_to_bridge(item["to"], item["message"])
            except Exception:  # noqa: BLE001
                ok = False
            if ok:
                sent += 1
            else:
                # Put it back at the tail and stop (bridge still down).
                await r.rpush(settings.WHATSAPP_QUEUE_KEY, raw)
                requeued += 1
                break
    finally:
        await r.aclose()
    return {"sent": sent, "requeued": requeued}
