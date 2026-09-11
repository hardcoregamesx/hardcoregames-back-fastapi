from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, conint

from ..database import get_session
from ..models import User, UserCustomized, PointTransaction, MembershipPointsClaim, YoutubeMembershipLink
from ..util.util_auth import get_current_user, get_current_complete_user

router = APIRouter(prefix="/users", tags=["user-points"])

# Puntos VIP por semana segun tier (bajo/medio = 1, alto = 2). Mismos tiers
# que MEMBERSHIP_DISCOUNT_PERCENT en products/views.py del repo django --
# si se cambia uno, cambiar el otro.
MEMBERSHIP_WEEKLY_POINTS = {
    "LOW": 1,
    "MID": 1,
    "HIGH": 2,
}


class MembershipPointsClaimResponse(BaseModel):
    points_awarded: int
    balance_after: int
    week_start_date: str


class PointsResponse(BaseModel):
    points: int
    balance_exchange: int


class ExchangePointsRequest(BaseModel):
    # Number of points the user wants to convert to balance.
    points_to_exchange: conint(gt=0)


class ExchangePointsResponse(BaseModel):
    points_before: int
    points_after: int
    balance_before: int
    balance_after: int
    exchanged_points: int
    exchanged_amount_cop: int


async def _get_or_create_user_customized(
    session: AsyncSession, current_user: User, for_update: bool = False
) -> UserCustomized:
    stmt = select(UserCustomized).where(UserCustomized.user_id == current_user.id)
    if for_update:
        # UserCustomized.user es lazy="joined": sin `of=`, Postgres rechaza el
        # FOR UPDATE por el LEFT OUTER JOIN hacia auth_user.
        stmt = stmt.with_for_update(of=UserCustomized)
    result = await session.execute(stmt)
    profile = result.scalars().first()

    if profile is None:
        # Create a new profile with 0 points and 0 balance
        profile = UserCustomized(user_id=current_user.id, puntos=0, balance_exchange=0)
        session.add(profile)
        await session.flush()

    return profile


@router.get("/me/points", response_model=PointsResponse)
async def get_my_points(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return current user's available points and balance_exchange."""

    print("current_user.id --->", current_user.id)
    result = await session.execute(
        select(UserCustomized).where(UserCustomized.user_id == current_user.id)
    )
    profile = result.scalars().first()

    if profile is None:
        return PointsResponse(points=0, balance_exchange=0)

    puntos = int(profile.puntos or 0)
    balance = int(profile.balance_exchange or 0)
    return PointsResponse(points=puntos, balance_exchange=balance)


@router.post("/me/exchange-points", response_model=ExchangePointsResponse)
async def exchange_points_for_balance(
    payload: ExchangePointsRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Exchange loyalty points for balance_exchange.

    Conversion rate: configurable via variable del sistema "puntos_pesos" (tabla products_variablessistema).

    The amount credited to `balance_exchange` is stored as an integer COP,
    so the calculated value is truncated to an integer (e.g. 3 points -> 1 COP).
    """

    # Row lock: two concurrent exchange requests must not both read the same
    # balance and both succeed (same reasoning as the roulette spin).
    profile = await _get_or_create_user_customized(session, current_user, for_update=True)

    if profile.puntos < payload.points_to_exchange:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tienes suficientes puntos para canjear.",
        )

    points_before = int(profile.puntos or 0)
    balance_before = int(profile.balance_exchange or 0)

    exchanged_points = int(payload.points_to_exchange)
    # Leer tasa de conversion desde variables del sistema (puntos_pesos)
    var_result = await session.execute(
        text(
            "SELECT valor FROM products_variablessistema "
            "WHERE nombre_variable = 'puntos_pesos' AND estado = true LIMIT 1"
        )
    )
    var_row = var_result.fetchone()
    cop_per_point = float(var_row[0]) if var_row else 0.5

    exchanged_amount_cop = int(exchanged_points * cop_per_point)

    # Update profile
    profile.puntos = points_before - exchanged_points
    profile.balance_exchange = balance_before + exchanged_amount_cop

    session.add(
        PointTransaction(
            user_id=current_user.id,
            delta=-exchanged_points,
            balance_after=profile.puntos,
            reason="EXCHANGE",
            reference_type="balance_exchange",
            reference_id=None,
            description=f"Canje de {exchanged_points} puntos por ${exchanged_amount_cop} COP de saldo",
        )
    )

    await session.commit()
    await session.refresh(profile)

    return ExchangePointsResponse(
        points_before=points_before,
        points_after=int(profile.puntos or 0),
        balance_before=balance_before,
        balance_after=int(profile.balance_exchange or 0),
        exchanged_points=exchanged_points,
        exchanged_amount_cop=exchanged_amount_cop,
    )


@router.post("/me/membership-points/claim", response_model=MembershipPointsClaimResponse)
async def claim_membership_points(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_complete_user),
):
    """Reclamo semanal de puntos VIP para miembros de YouTube con
    membresía activa. Usa-o-pierde: una semana no reclamada no se acumula
    -- el UniqueConstraint(user, week_start_date) es toda la lógica de
    'una vez por semana', dejando que la propia base rechace un segundo
    intento en vez de necesitar un SELECT previo con condición de carrera."""

    link_result = await session.execute(
        select(YoutubeMembershipLink).where(YoutubeMembershipLink.user_id == current_user.id)
    )
    link = link_result.scalars().first()
    if link is None or link.status != "ACTIVE" or not link.tier:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Necesitas una membresía de YouTube activa para reclamar estos puntos.",
        )

    points_to_award = MEMBERSHIP_WEEKLY_POINTS.get(link.tier, 0)
    if points_to_award <= 0:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tu nivel de membresía no otorga puntos VIP.")

    today = datetime.now(timezone.utc).date()
    week_start_date = today - timedelta(days=today.weekday())  # lunes de la semana ISO actual

    claim = MembershipPointsClaim(
        user_id=current_user.id,
        week_start_date=week_start_date,
        points_awarded=points_to_award,
        claimed_at=datetime.now(timezone.utc),
    )
    session.add(claim)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya reclamaste tus puntos VIP de esta semana.")

    # Mismo patron de bloqueo de fila que el canje de puntos, para que dos
    # reclamos concurrentes (aunque ya bloqueados por el UniqueConstraint de
    # arriba) nunca puedan pisarse el balance_after.
    profile = await _get_or_create_user_customized(session, current_user, for_update=True)
    points_after = int(profile.puntos or 0) + points_to_award
    profile.puntos = points_after

    session.add(
        PointTransaction(
            user_id=current_user.id,
            delta=points_to_award,
            balance_after=points_after,
            reason="YOUTUBE_MEMBER_CLAIM",
            reference_type="membership_points_claim",
            reference_id=str(claim.id) if claim.id else None,
            description=f"Reclamo semanal VIP ({link.tier}), semana del {week_start_date.isoformat()}",
        )
    )

    await session.commit()

    return MembershipPointsClaimResponse(
        points_awarded=points_to_award,
        balance_after=points_after,
        week_start_date=week_start_date.isoformat(),
    )
