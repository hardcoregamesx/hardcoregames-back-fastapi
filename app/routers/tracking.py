"""
tracking.py — Meta Conversions API (CAPI) relay endpoint.

Recibe eventos de compra del browser script (meta-pixel-tracking.js) y los
reenvía a la Graph API de Meta con el token de sistema. Así los eventos
llegan server-side para deduplicación iOS14 y mayor match rate.
"""

import os
import hashlib
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tracking", tags=["tracking"])

PIXEL_ID = "1242058424697245"
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
GRAPH_API_VERSION = "v19.0"
CAPI_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PIXEL_ID}/events"


class PurchaseEvent(BaseModel):
    order_id: Optional[str] = None
    event_id: Optional[str] = None
    event_source_url: Optional[str] = None
    fbp: Optional[str] = None
    fbc: Optional[str] = None
    email: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = "COP"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


@router.post("/purchase")
async def relay_purchase(event: PurchaseEvent, request: Request):
    """
    Recibe datos de compra del pixel del frontend y los reenvía a Meta CAPI.
    Falla en silencio para no afectar la experiencia del usuario.
    """
    if not META_ACCESS_TOKEN:
        logger.warning("[CAPI] META_ACCESS_TOKEN not configured — skipping relay")
        return {"status": "skipped", "reason": "token not configured"}

    event_id = event.event_id or f"purchase_{event.order_id or 'unknown'}"
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "")

    user_data = {
        "client_ip_address": client_ip.split(",")[0].strip() if client_ip else None,
        "client_user_agent": request.headers.get("User-Agent", ""),
        "fbp": event.fbp,
        "fbc": event.fbc,
    }
    if event.email:
        user_data["em"] = [_sha256(event.email)]

    # Remove None values
    user_data = {k: v for k, v in user_data.items() if v}

    custom_data = {"currency": event.currency or "COP"}
    if event.amount is not None:
        custom_data["value"] = event.amount
    if event.order_id:
        custom_data["order_id"] = event.order_id

    payload = {
        "data": [
            {
                "event_name": "Purchase",
                "event_time": int(__import__("time").time()),
                "event_id": event_id,
                "event_source_url": event.event_source_url or "https://www.hardcoregames.co",
                "action_source": "website",
                "user_data": user_data,
                "custom_data": custom_data,
            }
        ],
        "access_token": META_ACCESS_TOKEN,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(CAPI_URL, json=payload)
            if resp.status_code == 200:
                logger.info("[CAPI] Purchase event sent OK — event_id=%s", event_id)
                return {"status": "ok", "event_id": event_id}
            else:
                logger.warning("[CAPI] Meta returned %s: %s", resp.status_code, resp.text[:200])
                return {"status": "error", "code": resp.status_code}
    except Exception as exc:
        logger.error("[CAPI] Failed to send to Meta: %s", exc)
        return {"status": "error", "detail": str(exc)}
