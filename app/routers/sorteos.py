from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Sorteo, SorteoWinner, User
from ..services.sorteos import compute_progress
from ..util.util_auth import get_current_user, get_current_user_optional

router = APIRouter(prefix="/sorteos", tags=["sorteos"])


def _mask_email(email: str) -> str:
    """ju***@gmail.com — igual que se muestra a los demas clientes en la
    seccion de ganadores. Sin '@' (dato corrupto/vacio) se enmascara entero."""
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    visible = local[:2]
    return f"{visible}***@{domain}"


def _serialize_requirements(sorteo: Sorteo) -> dict:
    return {
        "min_purchases": sorteo.min_purchases,
        "min_amount": sorteo.min_amount,
        "require_both": sorteo.require_both,
    }


async def _serialize_winners(session: AsyncSession, sorteo_id: int) -> list[dict]:
    result = await session.execute(
        select(SorteoWinner, User)
        .join(User, SorteoWinner.user_id == User.id)
        .where(SorteoWinner.sorteo_id == sorteo_id)
        .order_by(SorteoWinner.drawn_at.asc())
    )
    winners = []
    for winner, user in result.all():
        full_name = f"{user.first_name} {user.last_name}".strip() or user.username
        winners.append(
            {
                "full_name": full_name,
                "email_masked": _mask_email(user.email),
                "drawn_at": winner.drawn_at.isoformat(),
            }
        )
    return winners


async def _serialize_sorteo(session: AsyncSession, sorteo: Sorteo, current_user: User | None) -> dict:
    data = {
        "id": sorteo.id,
        "title": sorteo.title,
        "legend": sorteo.legend,
        "prize_image_url": sorteo.prize_image_url,
        "start_date": sorteo.start_date.isoformat(),
        "end_date": sorteo.end_date.isoformat(),
        "status": sorteo.status,
        "winners_count": sorteo.winners_count,
        "requirements": _serialize_requirements(sorteo),
        "my_progress": None,
        "winners": [],
    }

    if sorteo.status == "FINISHED":
        data["winners"] = await _serialize_winners(session, sorteo.id)
    elif current_user is not None:
        progress = await compute_progress(session, sorteo, current_user.id)
        data["my_progress"] = {
            "purchases_count": progress.purchases_count,
            "amount_sum": progress.amount_sum,
            "qualified": progress.qualified,
        }

    return data


@router.get("/active")
async def list_active_sorteos(
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user_optional),
):
    result = await session.execute(
        select(Sorteo).where(Sorteo.status == "ACTIVE").order_by(Sorteo.end_date.asc())
    )
    sorteos = result.scalars().all()
    return {"data": [await _serialize_sorteo(session, s, current_user) for s in sorteos]}


@router.get("/{sorteo_id}")
async def get_sorteo(
    sorteo_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user_optional),
):
    sorteo = await session.get(Sorteo, sorteo_id)
    if sorteo is None or sorteo.status == "DRAFT":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sorteo no encontrado.")
    return await _serialize_sorteo(session, sorteo, current_user)


@router.get("/mine/widget")
async def get_my_widget_summary(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Resumen liviano para el boton flotante: solo lo que necesita para
    pintar el progreso (o el badge con la cantidad de sorteos activos)."""
    result = await session.execute(
        select(Sorteo).where(Sorteo.status == "ACTIVE").order_by(Sorteo.end_date.asc())
    )
    sorteos = result.scalars().all()

    items = []
    for sorteo in sorteos:
        progress = await compute_progress(session, sorteo, current_user.id)
        items.append(
            {
                "id": sorteo.id,
                "title": sorteo.title,
                "purchases_count": progress.purchases_count,
                "min_purchases": sorteo.min_purchases,
                "amount_sum": progress.amount_sum,
                "min_amount": sorteo.min_amount,
                "qualified": progress.qualified,
            }
        )

    return {"data": items}
