"""Beneficios para miembros pagos del canal de YouTube: conectar/desconectar
la cuenta y consultar el estado. El descuento de checkout vive en el repo
django (products/views.py); el reclamo semanal de puntos en user_points.py;
la ruleta VIP en rewards.py — este router es solo el ciclo de vida del
vínculo cuenta-hardcoregames <-> canal de YouTube.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import User, YoutubeMembershipLink
from ..util.util_auth import get_current_complete_user
from ..util.util_youtube import (
    YoutubeApiError,
    build_member_authorize_url,
    exchange_user_auth_code,
    sign_state,
    unsign_state,
)

router = APIRouter(prefix="/membership/youtube", tags=["membership"])

# A donde vuelve el navegador del miembro tras el consentimiento de Google,
# con o sin éxito. La UI real (toast + refetch de /status) vive en
# ProfilePage.tsx (frontend-v2), este endpoint solo pone la bandera en la URL.
FRONTEND_PROFILE_URL = "https://www.hardcoregames.co/profile"


def _serialize_link(link: YoutubeMembershipLink | None) -> dict:
    if link is None:
        return {"linked": False, "status": None, "tier": None, "linked_at": None, "last_synced_at": None}
    return {
        "linked": True,
        "status": link.status,
        "tier": link.tier,
        "youtube_display_name": link.youtube_display_name,
        "linked_at": link.linked_at.isoformat(),
        "last_synced_at": link.last_synced_at.isoformat() if link.last_synced_at else None,
    }


@router.get("/connect-url")
async def get_connect_url(current_user: User = Depends(get_current_complete_user)):
    """El botón 'Conectar YouTube' del perfil pide esta URL y redirige al
    navegador ahí — no se llama desde el propio backend."""
    state = sign_state(current_user.id)
    return {"authorize_url": build_member_authorize_url(state)}


@router.get("/callback")
async def oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Google redirige aquí tras el consentimiento del MIEMBRO. Público a
    propósito: la sesión JWT del sitio no viaja en este redirect, el usuario
    se recupera del `state` firmado."""

    if error:
        # El usuario canceló el consentimiento en la pantalla de Google.
        return RedirectResponse(f"{FRONTEND_PROFILE_URL}?youtube_linked=error&reason=cancelled")

    if not code or not state:
        return RedirectResponse(f"{FRONTEND_PROFILE_URL}?youtube_linked=error&reason=missing_params")

    try:
        user_id = unsign_state(state)
    except YoutubeApiError:
        return RedirectResponse(f"{FRONTEND_PROFILE_URL}?youtube_linked=error&reason=invalid_state")

    try:
        channel_id, display_name = await exchange_user_auth_code(code)
    except YoutubeApiError:
        return RedirectResponse(f"{FRONTEND_PROFILE_URL}?youtube_linked=error&reason=google_api")

    # ¿Ese canal ya está ligado a OTRA cuenta? El unique constraint de la
    # tabla es la fuente de verdad (se valida abajo con el IntegrityError);
    # esta consulta previa es solo para dar un mensaje mas claro sin
    # depender de parsear el texto del error de Postgres.
    existing_for_channel = await session.execute(
        select(YoutubeMembershipLink).where(YoutubeMembershipLink.youtube_channel_id == channel_id)
    )
    other_link = existing_for_channel.scalars().first()
    if other_link is not None and other_link.user_id != user_id:
        return RedirectResponse(f"{FRONTEND_PROFILE_URL}?youtube_linked=error&reason=channel_already_linked")

    own_link_result = await session.execute(
        select(YoutubeMembershipLink).where(YoutubeMembershipLink.user_id == user_id)
    )
    link = own_link_result.scalars().first()

    now = datetime.now(timezone.utc)
    if link is None:
        link = YoutubeMembershipLink(
            user_id=user_id,
            youtube_channel_id=channel_id,
            youtube_display_name=display_name,
            status="INACTIVE",  # el OAuth no prueba ser miembro pago; solo el sync diario lo confirma
            linked_at=now,
        )
        session.add(link)
    else:
        # Re-conectar (ej. cambió de canal): vuelve a INACTIVE hasta el
        # próximo sync, nunca se asume activo por haber completado OAuth.
        link.youtube_channel_id = channel_id
        link.youtube_display_name = display_name
        link.status = "INACTIVE"
        link.tier = None
        link.linked_at = now
        link.last_synced_at = None

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return RedirectResponse(f"{FRONTEND_PROFILE_URL}?youtube_linked=error&reason=channel_already_linked")

    return RedirectResponse(f"{FRONTEND_PROFILE_URL}?youtube_linked=1")


@router.get("/status")
async def get_status(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_complete_user),
):
    result = await session.execute(
        select(YoutubeMembershipLink).where(YoutubeMembershipLink.user_id == current_user.id)
    )
    link = result.scalars().first()
    return _serialize_link(link)


@router.post("/unlink")
async def unlink(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_complete_user),
):
    """Autoservicio: desvincula de inmediato. No borra puntos/cupones ya
    otorgados — nada que revertir, solo se bloquean reclamos/giros futuros
    (los gates de cada endpoint ya validan status == ACTIVE)."""
    result = await session.execute(
        select(YoutubeMembershipLink).where(YoutubeMembershipLink.user_id == current_user.id)
    )
    link = result.scalars().first()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No tienes una cuenta de YouTube conectada.")
    await session.delete(link)
    await session.commit()
    return {"unlinked": True}
