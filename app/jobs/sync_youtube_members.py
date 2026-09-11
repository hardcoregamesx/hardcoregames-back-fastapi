"""Sync diario contra la lista real de miembros pagos del canal de YouTube.

Invocacion (no hay precedente de cron sobre un contenedor FastAPI en este
VPS — el patron mas cercano es `docker exec hc-crm python -m jobs.run_all`
para el contenedor no-Django hc-crm, este job sigue el mismo estilo de
modulo suelto):

    docker exec hc-fastapi python -m app.jobs.sync_youtube_members

Crontab (agregar a mano en el VPS, no en codigo, y solo despues de haber
corrido esto una vez a mano contra produccion con exito):

    0 3 * * * /usr/bin/docker exec hc-fastapi python -m app.jobs.sync_youtube_members >> /opt/hardcoregames/youtube-sync.log 2>&1

No confiar en "el usuario completo el OAuth" como prueba de membresia paga
— este job, contra la Members API real del dueño del canal, es la UNICA
fuente de verdad para status=ACTIVE/INACTIVE y tier. Cada endpoint que
otorga un beneficio (descuento, reclamo de puntos, ruleta VIP) valida
status=='ACTIVE' en el momento de usarse, asi que este flip es toda la
logica de activacion/desactivacion — no hace falta ningun paso de reversion
aparte cuando alguien cancela.
"""

import asyncio
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from ..database import AsyncSessionLocal
from ..models import MembershipLevelMapping, YoutubeMembershipLink
from ..util.util_youtube import YoutubeApiError, fetch_current_members, refresh_creator_access_token


async def run() -> int:
    """Devuelve un exit code (0 = ok, 1 = fallo) para que el cron pueda
    detectar errores por el status del proceso, no solo por texto en el log."""

    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        try:
            access_token = await refresh_creator_access_token(session)
            current_members = await fetch_current_members(access_token)
        except YoutubeApiError as exc:
            print(f"[sync_youtube_members] ERROR consultando la Members API: {exc}", file=sys.stderr)
            return 1

        mapping_result = await session.execute(select(MembershipLevelMapping))
        level_to_tier = {row.google_level_name: row.tier for row in mapping_result.scalars().all()}

        links_result = await session.execute(select(YoutubeMembershipLink))
        links = list(links_result.scalars().all())

        activated = 0
        deactivated = 0
        unmapped_levels: set[str] = set()

        for link in links:
            level_name = current_members.get(link.youtube_channel_id)

            if level_name is None:
                # Ya no aparece en la lista de miembros pagos (cancelo, o
                # nunca lo fue): pierde el beneficio en esta misma corrida.
                if link.status != "INACTIVE":
                    deactivated += 1
                link.status = "INACTIVE"
                link.last_synced_at = now
                continue

            tier = level_to_tier.get(level_name)
            if tier is None:
                # Nivel real de YouTube Studio sin fila en MembershipLevelMapping
                # todavia (falta que el negocio la cargue en el admin) — no se
                # puede saber que descuento/puntos le corresponden, se deja
                # inactivo en vez de adivinar un tier.
                unmapped_levels.add(level_name)
                link.status = "INACTIVE"
                link.last_synced_at = now
                continue

            if link.status != "ACTIVE" or link.tier != tier:
                activated += 1
            link.status = "ACTIVE"
            link.tier = tier
            link.last_synced_at = now

        await session.commit()

        print(
            f"[sync_youtube_members] OK — {len(links)} vinculos revisados, "
            f"{activated} activados/actualizados, {deactivated} desactivados."
        )
        if unmapped_levels:
            print(
                "[sync_youtube_members] AVISO — niveles de YouTube sin mapear en "
                f"MembershipLevelMapping (cargar en el admin de Django): {sorted(unmapped_levels)}",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(run())
    sys.exit(exit_code)
