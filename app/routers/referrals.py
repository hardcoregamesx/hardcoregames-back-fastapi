"""Códigos de referido: cada usuario crea el suyo y ve lo que ha ganado.

El cashback (1% de lo pagado por el referido) lo acredita Django al confirmar el
pago (products/referrals.py); aquí solo se crea/consulta el código y se valida.
Tablas: ver docs/referidos.sql del repo django.
"""
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import User, UserCustomized
from ..util.util_auth import get_current_complete_user

router = APIRouter(prefix="/referrals", tags=["referrals"])

CODE_RE = re.compile(r"^[a-z0-9]{4,20}$")

# Rutas de un solo segmento del sitio (mantener alineado con RUTAS_UN_SEGMENTO en
# django/preventas/models.py) más palabras que no deben ser un código.
RESERVED = {
    "zelda", "grandtheftautovi", "fc27", "fc27ultimate", "gamepassultimate", "psplus", "fisicos", "rewards",
    "politica-tratamiento-datos", "2x1-playstation", "3x2-juegos", "beneficios", "cart", "catalogo",
    "cheap-games", "checkout", "destacados", "filters", "game-pass", "gamepass12meses", "guarantees", "help",
    "juegos-pc", "juegos-ps5", "juegos-xbox", "liked-games", "locura-playstation", "locura-xbox", "most-sold",
    "new-releases", "nintendo-switch", "points", "preventas", "profile", "purchases", "rifas", "sobre-pedido",
    "suscripciones", "week-offers", "admin", "api", "auth", "hardcore", "hardcoregames", "soporte", "oferta",
}


class CodeCreate(BaseModel):
    code: str


def _normalize(code: str) -> str:
    return (code or "").strip().lower()


@router.get("/validate/{code}")
async def validate_code(code: str, session: AsyncSession = Depends(get_session)):
    """Público: ¿existe este código de referido? (no revela de quién es)."""
    code = _normalize(code)
    if not CODE_RE.match(code):
        return {"valid": False}
    row = (await session.execute(text("SELECT 1 FROM referral_code WHERE code = :c"), {"c": code})).first()
    return {"valid": row is not None}


@router.get("/me")
async def my_referral(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_complete_user),
):
    row = (
        await session.execute(
            text("SELECT code, created_at FROM referral_code WHERE user_id = :u"), {"u": current_user.id}
        )
    ).first()
    stats = (
        await session.execute(
            text(
                "SELECT COALESCE(SUM(cashback) FILTER (WHERE status = 'credited'), 0) AS earned, "
                "COUNT(*) FILTER (WHERE status = 'credited') AS uses "
                "FROM referral_reward WHERE referrer_id = :u"
            ),
            {"u": current_user.id},
        )
    ).first()
    history = (
        await session.execute(
            text(
                "SELECT source_type, base_amount, cashback, status, created_at FROM referral_reward "
                "WHERE referrer_id = :u ORDER BY created_at DESC LIMIT 50"
            ),
            {"u": current_user.id},
        )
    ).all()
    balance = (
        await session.execute(
            text("SELECT balance_exchange FROM users_user_customized WHERE user_id = :u"), {"u": current_user.id}
        )
    ).scalar()
    return {
        "code": row[0] if row else None,
        "total_earned": int(stats[0]),
        "uses": int(stats[1]),
        "balance_exchange": int(balance or 0),
        "cashback_percent": 1,
        "history": [
            {
                "source_type": h[0],
                "base_amount": h[1],
                "cashback": h[2],
                "status": h[3],
                "created_at": h[4].isoformat() if h[4] else None,
            }
            for h in history
        ],
    }


@router.post("/me", status_code=status.HTTP_201_CREATED)
async def create_my_code(
    body: CodeCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_complete_user),
):
    """Crea el código del usuario. Solo una vez: cambiarlo rompería los links ya compartidos."""
    code = _normalize(body.code)
    if not CODE_RE.match(code):
        raise HTTPException(400, "El código debe tener entre 4 y 20 caracteres: solo letras y números, sin espacios.")
    if code in RESERVED:
        raise HTTPException(409, "Ese código no está disponible, elige otro.")

    already = (
        await session.execute(text("SELECT code FROM referral_code WHERE user_id = :u"), {"u": current_user.id})
    ).first()
    if already:
        raise HTTPException(409, "Ya tienes un código de referido.")

    # No puede chocar con un cupón (el catch-all /<algo> del sitio los trata como cupón) ni con
    # el enlace corto de una preventa.
    taken = (
        await session.execute(
            text(
                "SELECT 1 FROM coupons_coupon WHERE lower(name_coupon) = :c "
                "UNION ALL SELECT 1 FROM preventas_preventa WHERE lower(enlace_corto) = :c"
            ),
            {"c": code},
        )
    ).first()
    if taken:
        raise HTTPException(409, "Ese código no está disponible, elige otro.")

    # El perfil es donde se acredita el cashback: debe existir antes de poder ganarlo.
    profile = (
        await session.execute(
            text("SELECT 1 FROM users_user_customized WHERE user_id = :u"), {"u": current_user.id}
        )
    ).first()
    if profile is None:
        session.add(UserCustomized(user_id=current_user.id, puntos=0, balance_exchange=0))
        await session.flush()

    try:
        await session.execute(
            text("INSERT INTO referral_code (user_id, code) VALUES (:u, :c)"), {"u": current_user.id, "c": code}
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "Ese código ya está en uso, elige otro.")
    return {"code": code}
