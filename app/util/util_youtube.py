"""Cliente delgado contra Google OAuth2 / YouTube Data API v3, para el
modulo de beneficios de miembros pagos del canal.

Dos credenciales completamente distintas se manejan aqui, no confundirlas:

- La del MIEMBRO (el visitante de la tienda que conecta su cuenta): se usa
  una sola vez, en `exchange_user_auth_code`, solo para leer su propio
  channel_id. No se persiste ningun token del miembro.
- La del DUEÑO DEL CANAL (Hardcore Games): un refresh token capturado una
  sola vez a mano (fuera de esta app, ver Fase 0 del plan) con el scope
  `youtube.channel-memberships.creator`, guardado en
  `membership_googleoauthcredential` y usado solo por el cron diario
  (`app/jobs/sync_youtube_members.py`) para leer la lista real de miembros.
"""

import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import GoogleOAuthCredential
from .util_auth import SECRET_KEY

# Firma el `state` del flujo OAuth del miembro (mismo mecanismo que
# reset_serializer en util_auth.py, salt propia para no mezclar tokens de
# distintos flujos aunque comparta SECRET_KEY).
_state_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="youtube-oauth-state")
STATE_MAX_AGE_SECONDS = 600  # tiempo de sobra para completar el consentimiento de Google


def sign_state(user_id: int) -> str:
    return _state_serializer.dumps({"user_id": user_id})


def unsign_state(state: str) -> int:
    """Devuelve el user_id codificado en `state`, o levanta YoutubeApiError
    si esta vencido o fue manipulado."""
    try:
        data = _state_serializer.loads(state, max_age=STATE_MAX_AGE_SECONDS)
    except SignatureExpired:
        raise YoutubeApiError("El enlace de conexión con YouTube venció, intenta de nuevo.")
    except BadSignature:
        raise YoutubeApiError("El enlace de conexión con YouTube no es válido.")
    return data["user_id"]


GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_OAUTH_REDIRECT_URI = os.getenv(
    "GOOGLE_OAUTH_REDIRECT_URI", "https://api.hardcoregames.co/membership/youtube/callback"
)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_API_BASE = "https://youtube.googleapis.com/youtube/v3"

CREATOR_PROVIDER = "youtube_creator"

# Scope minimo para que un miembro cualquiera nos deje leer su propio
# channel_id — no pedimos nada mas, y el token se descarta tras usarlo.
MEMBER_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"


class YoutubeApiError(Exception):
    """Cualquier fallo de red/API de Google que un endpoint deba traducir a
    un HTTPException con un mensaje entendible, sin filtrar detalles internos."""


def build_member_authorize_url(state: str) -> str:
    """URL de consentimiento que ve el MIEMBRO al hacer clic en 'Conectar
    YouTube'. `state` ya viene firmado (ver util_auth-style serializer en el
    router) para sobrevivir el ida-y-vuelta del redirect sin CSRF."""

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": MEMBER_SCOPE,
        "access_type": "online",  # no hace falta refresh token del miembro, se descarta tras usarlo
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_user_auth_code(code: str) -> tuple[str, str]:
    """Cambia el `code` del miembro por su channel_id (y nombre visible).
    El access/refresh token que devuelve Google se usa una sola vez, aqui
    mismo, y nunca se guarda. Levanta YoutubeApiError si algo falla."""

    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
            },
        )
        if token_resp.status_code != 200:
            raise YoutubeApiError(f"Google token exchange failed: {token_resp.status_code} {token_resp.text}")
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise YoutubeApiError("Google token exchange sin access_token en la respuesta.")

        channel_resp = await client.get(
            f"{YOUTUBE_API_BASE}/channels",
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if channel_resp.status_code != 200:
            raise YoutubeApiError(f"channels.list falló: {channel_resp.status_code} {channel_resp.text}")
        items = channel_resp.json().get("items", [])
        if not items:
            raise YoutubeApiError("La cuenta de Google no tiene ningún canal de YouTube asociado.")

        channel_id = items[0]["id"]
        display_name = items[0].get("snippet", {}).get("title", "")
        return channel_id, display_name


async def _get_creator_credential(session: AsyncSession) -> GoogleOAuthCredential:
    result = await session.execute(
        select(GoogleOAuthCredential).where(GoogleOAuthCredential.provider == CREATOR_PROVIDER)
    )
    credential = result.scalars().first()
    if credential is None:
        raise YoutubeApiError(
            "No hay credencial 'youtube_creator' guardada — falta la captura manual del refresh token (Fase 0)."
        )
    return credential


async def refresh_creator_access_token(session: AsyncSession) -> str:
    """Devuelve un access_token vigente del DUEÑO DEL CANAL, refrescando y
    cacheando en `membership_googleoauthcredential` solo cuando hace falta."""

    credential = await _get_creator_credential(session)

    now = datetime.now(timezone.utc)
    if (
        credential.access_token_cache
        and credential.access_token_expires_at
        and credential.access_token_expires_at > now + timedelta(minutes=2)
    ):
        return credential.access_token_cache

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": credential.refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if resp.status_code != 200:
        raise YoutubeApiError(f"No se pudo refrescar el access_token del creador: {resp.status_code} {resp.text}")

    payload = resp.json()
    access_token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 3600))

    credential.access_token_cache = access_token
    credential.access_token_expires_at = now + timedelta(seconds=expires_in)
    credential.updated_at = now
    await session.commit()

    return access_token


async def fetch_current_members(access_token: str) -> dict[str, str]:
    """Trae la lista completa (paginada) de miembros pagos actuales del
    canal. Devuelve {channel_id: nombre_del_nivel_en_youtube_studio} — el
    nombre del nivel es texto libre que definio el dueño del canal, hay que
    mapearlo via MembershipLevelMapping antes de usarlo como tier interno."""

    members: dict[str, str] = {}
    page_token: str | None = None

    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            params = {"part": "snippet", "maxResults": "1000"}
            if page_token:
                params["pageToken"] = page_token
            resp = await client.get(
                f"{YOUTUBE_API_BASE}/members",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                raise YoutubeApiError(f"members.list falló: {resp.status_code} {resp.text}")

            payload = resp.json()
            for item in payload.get("items", []):
                snippet = item.get("snippet", {})
                member_details = snippet.get("memberDetails", {})
                channel_id = member_details.get("channelId")
                level_name = snippet.get("membershipsDetails", {}).get("highestAccessibleLevel")
                if channel_id and level_name:
                    members[channel_id] = level_name

            page_token = payload.get("nextPageToken")
            if not page_token:
                break

    return members
