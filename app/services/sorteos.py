"""Calculo de progreso de participacion en un sorteo.

La calificacion de un usuario nunca se materializa en una tabla propia:
se recalcula en vivo contra Transactions (el dinero real cobrado por
checkout, via Bold o el ePayco legacy) cada vez que se pide. Esto es lo
que permite que un reembolso o cancelacion posterior a que un cliente ya
hubiera calificado lo saque de la lista automaticamente, sin job de
sincronizacion ni riesgo de que quede desactualizado.

Una "compra" es una transaccion (un checkout), no una linea de producto:
un carrito con 2 productos cuenta como 1 compra, no 2. El monto es lo que
realmente se cobro (neto de saldo/cupon aplicado), no el precio de
catalogo -- por eso NO se calcula contra SaleDetail (la compra real, pero
sin monto) ni contra OrderBuy/orders_buy (tabla practicamente vacia en
produccion, con amount que nunca se llena).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Sorteo, Transactions

# Estados de pago exitoso vistos en produccion entre los dos gateways que ha
# usado la tienda (Bold via webhook/redirect, y el ePayco legacy que todavia
# deja filas). Verificado con
# SELECT status, COUNT(*) FROM products_transactions GROUP BY status.
TRANSACTION_SUCCESS_STATUSES = ("approved", "SALE_APPROVED", "aceptada", "accepted")


@dataclass
class SorteoProgress:
    purchases_count: int
    amount_sum: int
    qualified: bool


async def compute_progress(session: AsyncSession, sorteo: Sorteo, user_id: int) -> SorteoProgress:
    result = await session.execute(
        select(
            func.count(Transactions.id_transaction),
            func.coalesce(func.sum(Transactions.amount), 0),
        ).where(
            Transactions.user_id == user_id,
            Transactions.status.in_(TRANSACTION_SUCCESS_STATUSES),
            Transactions.date_transaction >= sorteo.start_date,
            Transactions.date_transaction <= sorteo.end_date,
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
