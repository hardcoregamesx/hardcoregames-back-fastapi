"""Calculo de progreso de participacion en un sorteo.

La calificacion de un usuario nunca se materializa en una tabla propia:
se recalcula en vivo contra OrderBuy cada vez que se pide. Esto es lo que
permite que un reembolso o cancelacion posterior a que un cliente ya
hubiera calificado lo saque de la lista automaticamente, sin job de
sincronizacion ni riesgo de que quede desactualizado.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OrderBuy, Sorteo

STATUS_COMPLETADO = "completed"


@dataclass
class SorteoProgress:
    purchases_count: int
    amount_sum: int
    qualified: bool


async def compute_progress(session: AsyncSession, sorteo: Sorteo, user_id: int) -> SorteoProgress:
    result = await session.execute(
        select(
            func.count(OrderBuy.id_order),
            func.coalesce(func.sum(OrderBuy.amount), 0),
        ).where(
            OrderBuy.user_id == user_id,
            OrderBuy.status == STATUS_COMPLETADO,
            OrderBuy.created_at >= sorteo.start_date,
            OrderBuy.created_at <= sorteo.end_date,
        )
    )
    purchases_count, amount_sum = result.one()
    purchases_count = int(purchases_count or 0)
    amount_sum = int(amount_sum or 0)

    has_count_req = sorteo.min_purchases is not None
    has_amount_req = sorteo.min_amount is not None
    count_ok = (not has_count_req) or purchases_count >= sorteo.min_purchases
    amount_ok = (not has_amount_req) or amount_sum >= sorteo.min_amount

    if has_count_req and has_amount_req:
        qualified = (count_ok and amount_ok) if sorteo.require_both else (count_ok or amount_ok)
    else:
        qualified = count_ok and amount_ok

    return SorteoProgress(purchases_count=purchases_count, amount_sum=amount_sum, qualified=qualified)
