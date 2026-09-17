"""Endpoints de lectura de planes de pago (cuotas y reserva).

Fase 1 de docs/cuotas-y-reserva.md (ver tambien hardcoregames-back/docs/
cuotas-y-reserva.md, la fuente de verdad del proyecto completo). Django es
quien cobra y confirma pagos (checkout, webhooks, `planes/cuotaTransferencia
Create/`, etc. -- ver §4 de la spec); este router solo lee y expone lo que
el frontend necesita para pintar "Pagos pendientes" y la pantalla de un plan
por token, sin login, para invitados.
"""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import GameDetail, PaymentInstallment, PaymentPlan, Product, User, UserCustomized
from app.util.util_auth import get_current_user

router = APIRouter(prefix="/payment-plans", tags=["payment-plans"])


class InstallmentRead(BaseModel):
    id: int
    numero: int
    monto: int
    mora: int
    fecha_vencimiento: date | None = None
    estado: str
    fecha_pago: datetime | None = None

    class Config:
        orm_mode = True


class PlanRead(BaseModel):
    id: int
    tipo: str
    estado: str
    titulo_snapshot: str
    # Titulo/imagen VIVOS del producto (pueden diferir de titulo_snapshot si
    # el producto se renombro despues de crear el plan). Nombrados distinto
    # a proposito para no confundirlos con el snapshot congelado.
    producto_titulo: str | None = None
    producto_imagen: str | None = None
    precio_total: int
    descuento: int
    total_pagado: int
    mora_acumulada: int
    retirado: bool
    token: str
    fecha_creacion: datetime
    fecha_lanzamiento: date | None = None
    cuotas: list[InstallmentRead]
    proxima_cuota: InstallmentRead | None = None
    puede_pagar: bool

    class Config:
        orm_mode = True


class PlanByTokenRead(PlanRead):
    user_email: str | None = None
    is_guest_account: bool = False


class PendingCountResponse(BaseModel):
    count: int


def _mask_email(email: str | None) -> str | None:
    """"ju***@gmail.com" -- se muestra en la pantalla de un plan abierto por
    token (sin login), para confirmar de quien es sin exponer el correo
    completo."""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    visible = local[:2]
    return f"{visible}***@{domain}"


def _proxima_cuota(installments: list[PaymentInstallment]) -> PaymentInstallment | None:
    """La cuota pendiente con fecha de vencimiento mas antigua. Una cuota
    pendiente sin fecha (el saldo de una reserva antes de asignar cuenta,
    §3.2) no cuenta: no hay "proxima fecha" que mostrar todavia."""
    pendientes = [
        c for c in installments
        if c.estado == "pendiente" and c.fecha_vencimiento is not None
    ]
    if not pendientes:
        return None
    return min(pendientes, key=lambda c: c.fecha_vencimiento)


def _puede_pagar(plan: PaymentPlan, installments: list[PaymentInstallment]) -> bool:
    hay_pendiente_con_fecha = any(
        c.estado == "pendiente" and c.fecha_vencimiento is not None for c in installments
    )
    reserva_asignada = plan.tipo == "reserva" and plan.estado == "asignado"
    return hay_pendiente_con_fecha or reserva_asignada


def _build_plan_read(plan, producto_titulo, producto_imagen, fecha_lanzamiento, installments):
    cuotas = sorted(installments, key=lambda c: c.numero)
    proxima = _proxima_cuota(installments)
    return PlanRead(
        id=plan.id,
        tipo=plan.tipo,
        estado=plan.estado,
        titulo_snapshot=plan.titulo_snapshot,
        producto_titulo=producto_titulo,
        producto_imagen=producto_imagen,
        precio_total=plan.precio_total,
        descuento=plan.descuento,
        total_pagado=plan.total_pagado,
        mora_acumulada=plan.mora_acumulada,
        retirado=plan.retirado,
        token=plan.token,
        fecha_creacion=plan.fecha_creacion,
        fecha_lanzamiento=fecha_lanzamiento,
        cuotas=[InstallmentRead.from_orm(c) for c in cuotas],
        proxima_cuota=InstallmentRead.from_orm(proxima) if proxima else None,
        puede_pagar=_puede_pagar(plan, installments),
    )


async def _load_plans_with_details(
    session: AsyncSession, plans: list[PaymentPlan]
) -> list[PlanRead]:
    """Arma el shape de respuesta para una tanda de planes con dos consultas
    agrupadas (producto de cada gamedetail_id, cuotas de cada plan_id) --
    nunca una consulta por plan, ni siquiera cuando la lista viene de
    ``GET /payment-plans/`` con varios planes del mismo usuario."""
    if not plans:
        return []

    gamedetail_ids = list({p.gamedetail_id for p in plans})
    plan_ids = [p.id for p in plans]

    product_result = await session.execute(
        select(
            GameDetail.id_game_detail,
            Product.title,
            Product.image,
            Product.fecha_lanzamiento,
        )
        .select_from(GameDetail)
        .join(Product, Product.id_product == GameDetail.producto_id, isouter=True)
        .where(GameDetail.id_game_detail.in_(gamedetail_ids))
    )
    product_map = {
        row.id_game_detail: (row.title, row.image, row.fecha_lanzamiento)
        for row in product_result.all()
    }

    installments_result = await session.execute(
        select(PaymentInstallment).where(PaymentInstallment.plan_id.in_(plan_ids))
    )
    installments_by_plan: dict[int, list[PaymentInstallment]] = {}
    for inst in installments_result.scalars().all():
        installments_by_plan.setdefault(inst.plan_id, []).append(inst)

    out: list[PlanRead] = []
    for plan in plans:
        titulo, imagen, fecha_lanzamiento = product_map.get(plan.gamedetail_id, (None, None, None))
        out.append(
            _build_plan_read(
                plan, titulo, imagen, fecha_lanzamiento,
                installments_by_plan.get(plan.id, []),
            )
        )
    return out


def _sort_key_proxima(plan_read: PlanRead):
    """Orden por proximo vencimiento (§5): los que tienen una fecha concreta
    primero, de mas cercana a mas lejana; el resto (reservas esperando
    stock, planes completados/cancelados/retirados) al final."""
    if plan_read.proxima_cuota and plan_read.proxima_cuota.fecha_vencimiento:
        return (0, plan_read.proxima_cuota.fecha_vencimiento)
    return (1, date.max)


@router.get("/", response_model=list[PlanRead])
async def list_my_payment_plans(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Planes del usuario autenticado, con sus cuotas, para la pagina
    ``/pagos`` y el botón dorado "Pagos pendientes" en ``/purchases``."""
    result = await session.execute(
        select(PaymentPlan).where(PaymentPlan.user_id == current_user.id)
    )
    plans = result.scalars().all()
    plan_reads = await _load_plans_with_details(session, plans)
    plan_reads.sort(key=_sort_key_proxima)
    return plan_reads


@router.get("/pending-count", response_model=PendingCountResponse)
async def pending_installments_count(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Cuotas pendientes ya vencidas o que vencen en <=7 dias, de planes no
    completados/cancelados/retirados del usuario -- alimenta el badge del
    botón dorado "Pagos pendientes"."""
    limite = datetime.utcnow().date() + timedelta(days=7)
    result = await session.execute(
        select(func.count(PaymentInstallment.id))
        .select_from(PaymentInstallment)
        .join(PaymentPlan, PaymentPlan.id == PaymentInstallment.plan_id)
        .where(
            PaymentPlan.user_id == current_user.id,
            PaymentPlan.retirado.is_(False),
            PaymentPlan.estado.notin_(["completado", "cancelado"]),
            PaymentInstallment.estado == "pendiente",
            PaymentInstallment.fecha_vencimiento.is_not(None),
            PaymentInstallment.fecha_vencimiento <= limite,
        )
    )
    count = result.scalar() or 0
    return PendingCountResponse(count=count)


@router.get("/by-token/{token}", response_model=PlanByTokenRead)
async def get_payment_plan_by_token(
    token: str,
    session: AsyncSession = Depends(get_session),
):
    """Un plan sin login, para el enlace de correo
    ``https://www.hardcoregames.co/pagos/<token>`` (invitados incluidos)."""
    result = await session.execute(select(PaymentPlan).where(PaymentPlan.token == token))
    plan = result.scalars().first()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan no encontrado.")

    plan_reads = await _load_plans_with_details(session, [plan])
    base = plan_reads[0]

    user_result = await session.execute(select(User).where(User.id == plan.user_id))
    user = user_result.scalars().first()

    profile_result = await session.execute(
        select(UserCustomized).where(UserCustomized.user_id == plan.user_id)
    )
    profile = profile_result.scalars().first()

    return PlanByTokenRead(
        **base.dict(),
        user_email=_mask_email(user.email if user else None),
        is_guest_account=bool(profile.is_guest_account) if profile else False,
    )
