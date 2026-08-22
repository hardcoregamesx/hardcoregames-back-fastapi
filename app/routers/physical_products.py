"""Catálogo de productos físicos (consolas, juegos, accesorios usados/nuevos).

Fuente de verdad: un Google Sheet público de solo lectura
("JUEGOS, CONSOLAS Y ACCESORIOS"), administrado a mano por el equipo de
ventas. No hay tabla propia ni escritura desde este servicio: se lee el CSV
exportado, se limpia y se cachea en memoria un rato para no golpear a Google
en cada visita a la página.

Estos productos NO pasan por el checkout/carrito digital ni por Bold: el
pago es en efectivo o transferencia, coordinado por WhatsApp. Por eso el
recargo de transferencia se calcula aquí y se sirve ya resuelto.
"""

import csv
import io
import re
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/products/physical", tags=["physical-products"])

SHEET_ID = "1nqroaF8p2FYTfBSI5xep9Sf92mYNzutHCvIhBX295hA"
SHEET_GID = "0"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"

# Solo aplica a productos con precio en efectivo superior a este umbral.
TRANSFER_SURCHARGE = 50_000
TRANSFER_SURCHARGE_MIN_PRICE = 600_000

_CACHE_TTL_SECONDS = 300
_cache: dict = {"data": None, "fetched_at": 0.0}

_SOLD_OUT_RE = re.compile(r"AGOTAD|VENDID", re.IGNORECASE)


def _parse_price(raw: str) -> int | None:
    raw = (raw or "").strip()
    if not raw or _SOLD_OUT_RE.search(raw):
        return None
    cleaned = raw.replace("$", "").replace(" ", "").replace(",", "")
    try:
        return int(round(float(cleaned)))
    except ValueError:
        return None


def _clean_image(raw: str) -> str | None:
    raw = (raw or "").strip()
    # El sheet tiene celdas con texto tipo "CLICK AQUI" en vez de una URL real
    # (era un hyperlink en Sheets; el CSV solo exporta el texto visible).
    if raw.lower().startswith("http"):
        return raw
    return None


def _is_section_row(product: str, price: str, status: str, location: str) -> bool:
    """Filas que no son productos: encabezados de sección repetidos
    ("NINTENDO SWITCH 2,PRECIO,ESTADO,..."), separadores por categoría
    ("CONTROLES Y ACCESORIOS XBOX") o notas informativas del sheet."""
    if not product.strip():
        return True
    if price.strip().upper() == "PRECIO":
        return True
    if not price.strip() and not status.strip() and not location.strip():
        return True
    return False


def _parse_csv(text: str) -> list[dict]:
    rows = list(csv.reader(io.StringIO(text)))
    products = []
    for row in rows[1:]:
        row = row + [""] * (7 - len(row))  # tolera filas más cortas
        product, price_raw, status_raw, has_box_raw, location_raw, image_raw, platform_raw = row[:7]

        if _is_section_row(product, price_raw, status_raw, location_raw):
            continue

        sold_out = bool(_SOLD_OUT_RE.search(f"{price_raw} {status_raw}"))
        price_cash = None if sold_out else _parse_price(price_raw)
        if not sold_out and price_cash is None:
            # precio no legible y no está marcado agotado: dato roto, se omite
            continue

        price_transfer = None
        if price_cash is not None:
            surcharge = TRANSFER_SURCHARGE if price_cash > TRANSFER_SURCHARGE_MIN_PRICE else 0
            price_transfer = price_cash + surcharge

        products.append(
            {
                "name": product.strip(),
                "available": not sold_out,
                "price_cash": price_cash,
                "price_transfer": price_transfer,
                "condition": status_raw.strip() or None,
                "has_box": has_box_raw.strip() or None,
                "location": location_raw.strip() or None,
                "platform": platform_raw.strip() or None,
                "image_url": _clean_image(image_raw),
            }
        )
    return products


async def _fetch_products() -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(CSV_URL)
        resp.raise_for_status()
    return _parse_csv(resp.content.decode("utf-8"))


@router.get("")
async def list_physical_products():
    now = time.time()
    stale = _cache["data"] is None or (now - _cache["fetched_at"]) > _CACHE_TTL_SECONDS
    if stale:
        try:
            products = await _fetch_products()
        except (httpx.HTTPError, UnicodeDecodeError):
            if _cache["data"] is not None:
                return _cache["data"]
            raise HTTPException(status_code=502, detail="No se pudo leer el catálogo de productos físicos")
        _cache["data"] = {
            "products": products,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _cache["fetched_at"] = now
    return _cache["data"]
