import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import (
    User,
    UserCustomized,
    Coupon,
    PointTransaction,
    Roulette,
    RoulettePrize,
    RouletteSpin,
)
from ..util.util_auth import get_current_user, get_current_complete_user

router = APIRouter(prefix="/rewards", tags=["rewards"])

DEFAULT_COUPON_VALIDITY_MINUTES = 60


# ============================================================================
# Helpers
# ============================================================================

async def _get_or_create_profile(session: AsyncSession, user_id: int, for_update: bool = False) -> UserCustomized:
    stmt = select(UserCustomized).where(UserCustomized.user_id == user_id)
    if for_update:
        # UserCustomized.user es lazy="joined": sin `of=`, Postgres rechaza el
        # FOR UPDATE porque arrastra el LEFT OUTER JOIN hacia auth_user
        # ("cannot be applied to the nullable side of an outer join").
        # Bloqueando explicitamente solo esta tabla se evita el problema.
        stmt = stmt.with_for_update(of=UserCustomized)
    result = await session.execute(stmt)
    profile = result.scalars().first()
    if profile is None:
        profile = UserCustomized(user_id=user_id, puntos=0, balance_exchange=0)
        session.add(profile)
        await session.flush()
    return profile


async def _record_points(
    session: AsyncSession,
    user_id: int,
    delta: int,
    balance_after: int,
    reason: str,
    reference_type: str | None = None,
    reference_id: str | None = None,
    description: str = "",
) -> None:
    session.add(
        PointTransaction(
            user_id=user_id,
            delta=delta,
            balance_after=balance_after,
            reason=reason,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )
    )


def _pick_weighted_prize(prizes: list[RoulettePrize]) -> RoulettePrize:
    eligible = [p for p in prizes if p.stock is None or p.stock > 0]
    if not eligible:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No hay premios disponibles en este momento.",
        )
    total_weight = sum(p.weight for p in eligible)
    if total_weight <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La ruleta no está configurada correctamente.",
        )
    roll = random.SystemRandom().uniform(0, total_weight)
    cumulative = 0
    for prize in eligible:
        cumulative += prize.weight
        if roll <= cumulative:
            return prize
    return eligible[-1]


def _serialize_prize_public(p: RoulettePrize) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "color": p.color,
        "display_order": p.display_order,
    }


def _serialize_spin_result(spin: RouletteSpin, prize: RoulettePrize, coupon: Coupon | None, points_after: int) -> dict:
    return {
        "spin_id": spin.id,
        "prize": {
            "id": prize.id,
            "name": prize.name,
            "prize_type": prize.prize_type,
            "color": prize.color,
        },
        "coupon": (
            {
                "code": coupon.name_coupon,
                "discount_type": coupon.discount_type,
                "fixed_amount": coupon.fixed_amount,
                "percentage_off": coupon.percentage_off,
                "expiration_date": coupon.expiration_date.isoformat(),
            }
            if coupon
            else None
        ),
        "claim_message": (
            f"Escríbenos por WhatsApp con tu código de giro #{spin.id} para reclamar tu premio."
            if prize.prize_type == "MANUAL_CLAIM"
            else None
        ),
        "points_after": points_after,
    }


# ============================================================================
# GET /rewards/roulette — public config for rendering the wheel
# ============================================================================

@router.get("/roulette")
async def get_roulette_config(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    result = await session.execute(
        select(Roulette).where(Roulette.is_active.is_(True)).order_by(Roulette.id.desc())
    )
    roulette = result.scalars().first()
    if not roulette:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay una ruleta activa.")

    prizes_result = await session.execute(
        select(RoulettePrize)
        .where(RoulettePrize.roulette_id == roulette.id, RoulettePrize.is_active.is_(True))
        .order_by(RoulettePrize.display_order.asc())
    )
    prizes = prizes_result.scalars().all()

    profile = await _get_or_create_profile(session, current_user.id)
    await session.commit()

    spins_today = 0
    if roulette.max_spins_per_day:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        count_result = await session.execute(
            select(func.count(RouletteSpin.id)).where(
                RouletteSpin.user_id == current_user.id,
                RouletteSpin.roulette_id == roulette.id,
                RouletteSpin.created_at >= today_start,
            )
        )
        spins_today = count_result.scalar() or 0

    return {
        "roulette_id": roulette.id,
        "name": roulette.name,
        "cost_points": roulette.cost_points,
        "max_spins_per_day": roulette.max_spins_per_day,
        "spins_today": spins_today,
        "user_points": int(profile.puntos or 0),
        "prizes": [_serialize_prize_public(p) for p in prizes],
    }


# ============================================================================
# POST /rewards/roulette/spin — the only place a prize is decided
# ============================================================================

class SpinRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=8, max_length=100)


@router.post("/roulette/spin")
async def spin_roulette(
    payload: SpinRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_complete_user),
):
    # Safe retry: if this idempotency_key was already processed, return the
    # same result instead of charging the user again.
    existing = await session.execute(
        select(RouletteSpin).where(RouletteSpin.idempotency_key == payload.idempotency_key)
    )
    existing_spin = existing.scalars().first()
    if existing_spin:
        if existing_spin.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Clave de idempotencia inválida.")
        prize_result = await session.execute(
            select(RoulettePrize).where(RoulettePrize.id == existing_spin.prize_id)
        )
        prize = prize_result.scalars().first()
        coupon = None
        if existing_spin.coupon_id:
            coupon_result = await session.execute(select(Coupon).where(Coupon.id_coupon == existing_spin.coupon_id))
            coupon = coupon_result.scalars().first()
        profile = await _get_or_create_profile(session, current_user.id)
        return _serialize_spin_result(existing_spin, prize, coupon, int(profile.puntos or 0))

    roulette_result = await session.execute(
        select(Roulette).where(Roulette.is_active.is_(True)).order_by(Roulette.id.desc())
    )
    roulette = roulette_result.scalars().first()
    if not roulette:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay una ruleta activa.")

    if roulette.max_spins_per_day:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        count_result = await session.execute(
            select(func.count(RouletteSpin.id)).where(
                RouletteSpin.user_id == current_user.id,
                RouletteSpin.roulette_id == roulette.id,
                RouletteSpin.created_at >= today_start,
            )
        )
        if (count_result.scalar() or 0) >= roulette.max_spins_per_day:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Alcanzaste el máximo de giros de hoy.",
            )

    # Row lock: two concurrent spins for the same user must not both read the
    # same balance and both succeed.
    profile = await _get_or_create_profile(session, current_user.id, for_update=True)

    if int(profile.puntos or 0) < roulette.cost_points:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tienes suficientes puntos para girar la ruleta.",
        )

    prizes_result = await session.execute(
        select(RoulettePrize).where(RoulettePrize.roulette_id == roulette.id, RoulettePrize.is_active.is_(True))
    )
    prizes = list(prizes_result.scalars().all())

    # Enforce max_per_user: exclude prizes this user already exhausted.
    limited_prize_ids = [p.id for p in prizes if p.max_per_user is not None]
    user_prize_counts: dict[int, int] = {}
    if limited_prize_ids:
        counts_result = await session.execute(
            select(RouletteSpin.prize_id, func.count(RouletteSpin.id))
            .where(RouletteSpin.user_id == current_user.id, RouletteSpin.prize_id.in_(limited_prize_ids))
            .group_by(RouletteSpin.prize_id)
        )
        user_prize_counts = dict(counts_result.all())

    eligible_prizes = [
        p for p in prizes
        if p.max_per_user is None or user_prize_counts.get(p.id, 0) < p.max_per_user
    ]
    prize = _pick_weighted_prize(eligible_prizes)

    points_before = int(profile.puntos or 0)
    points_after = points_before - roulette.cost_points
    profile.puntos = points_after

    await _record_points(
        session,
        user_id=current_user.id,
        delta=-roulette.cost_points,
        balance_after=points_after,
        reason="ROULETTE_SPIN",
        reference_type="roulette",
        reference_id=str(roulette.id),
        description=f"Giro de ruleta: {roulette.name}",
    )

    coupon: Coupon | None = None
    if prize.prize_type in ("COUPON_FIXED", "COUPON_PERCENT"):
        validity_minutes = prize.coupon_validity_minutes or DEFAULT_COUPON_VALIDITY_MINUTES
        expiration = datetime.now(timezone.utc) + timedelta(minutes=validity_minutes)
        coupon = Coupon(
            name_coupon=f"RUL-{current_user.id}-{int(datetime.now(timezone.utc).timestamp())}",
            expiration_date=expiration,
            is_valid=True,
            user_id=current_user.id,
            discount_type="FIXED_AMOUNT" if prize.prize_type == "COUPON_FIXED" else "PERCENTAGE",
            fixed_amount=prize.value if prize.prize_type == "COUPON_FIXED" else 0,
            percentage_off=prize.value if prize.prize_type == "COUPON_PERCENT" else 0,
            source="ROULETTE",
        )
        session.add(coupon)
        await session.flush()
    elif prize.prize_type == "POINTS":
        points_after += prize.value
        profile.puntos = points_after
        await _record_points(
            session,
            user_id=current_user.id,
            delta=prize.value,
            balance_after=points_after,
            reason="ROULETTE_SPIN",
            reference_type="roulette_prize",
            reference_id=str(prize.id),
            description=f"Premio de ruleta: {prize.name}",
        )

    if prize.stock is not None:
        prize.stock = prize.stock - 1

    spin = RouletteSpin(
        user_id=current_user.id,
        roulette_id=roulette.id,
        prize_id=prize.id,
        points_spent=roulette.cost_points,
        coupon_id=coupon.id_coupon if coupon else None,
        idempotency_key=payload.idempotency_key,
    )
    session.add(spin)

    try:
        await session.commit()
    except IntegrityError:
        # Concurrent request beat us to the same idempotency_key.
        await session.rollback()
        existing = await session.execute(
            select(RouletteSpin).where(RouletteSpin.idempotency_key == payload.idempotency_key)
        )
        existing_spin = existing.scalars().first()
        if not existing_spin:
            raise
        prize_result = await session.execute(select(RoulettePrize).where(RoulettePrize.id == existing_spin.prize_id))
        prize = prize_result.scalars().first()
        coupon = None
        if existing_spin.coupon_id:
            coupon_result = await session.execute(select(Coupon).where(Coupon.id_coupon == existing_spin.coupon_id))
            coupon = coupon_result.scalars().first()
        profile = await _get_or_create_profile(session, current_user.id)
        return _serialize_spin_result(existing_spin, prize, coupon, int(profile.puntos or 0))

    await session.refresh(spin)
    return _serialize_spin_result(spin, prize, coupon, points_after)


# ============================================================================
# GET /rewards/points/history
# ============================================================================

@router.get("/points/history")
async def get_points_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    result = await session.execute(
        select(PointTransaction)
        .where(PointTransaction.user_id == current_user.id)
        .order_by(PointTransaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = result.scalars().all()
    return {
        "data": [
            {
                "id": t.id,
                "delta": t.delta,
                "balance_after": t.balance_after,
                "reason": t.reason,
                "description": t.description,
                "created_at": t.created_at.isoformat(),
            }
            for t in rows
        ]
    }


# ============================================================================
# GET /rewards/coupons/mine
# ============================================================================

@router.get("/coupons/mine")
async def get_my_coupons(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(Coupon)
        .where(
            Coupon.user_id == current_user.id,
            Coupon.is_valid.is_(True),
            Coupon.expiration_date > now,
        )
        .order_by(Coupon.expiration_date.asc())
    )
    coupons = result.scalars().all()
    return {
        "data": [
            {
                "code": c.name_coupon,
                "discount_type": c.discount_type,
                "fixed_amount": c.fixed_amount,
                "percentage_off": c.percentage_off,
                "source": c.source,
                "expiration_date": c.expiration_date.isoformat(),
            }
            for c in coupons
        ]
    }
