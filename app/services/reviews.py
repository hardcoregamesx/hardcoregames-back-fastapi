"""Reglas de las reseñas de producto (puras, sin base de datos).

Las reseñas son sobre el JUEGO. Un comentario que habla del servicio de la
tienda (entrega, atención, garantía, soporte...) no se publica, sea elogio o
queja: se filtra por TEMA y no por tono, para no mostrar solo lo bueno del
servicio ni solo lo malo. Las estrellas siempre cuentan.

El filtro es una lista de palabras y, ante la duda, oculta: un falso positivo
solo esconde un comentario (la nota sigue contando); un falso negativo publica
algo que no es del juego.
"""
from __future__ import annotations

import re
import unicodedata

MAX_COMMENT_LENGTH = 300

# Raíces sobre texto sin acentos y en minúsculas.
_SERVICE_PATTERN = re.compile(
    r"\b("
    r"servicio\w*|atencion|atendi\w*|atienden|atender|"
    r"entreg\w*|envi[oa]\w*|demor\w*|tard[aeo]\w*|rapidez|"
    r"garantia\w*|soporte|"
    r"whatsapp|wasap|"
    r"vendedor\w*|tienda\w*|pagina|asesor\w*|trato|"
    r"respuesta\w*|respond\w*|"
    r"estafa\w*|robo|robar\w*|reembols\w*|devoluc\w*|cobr\w*|"
    r"hardcore\w*"
    r")\b"
)
_LINK_PATTERN = re.compile(r"(https?://|www\.|\.com\b|\.co\b)", re.IGNORECASE)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _fold(text: str) -> str:
    """Minúsculas y sin acentos, para comparar."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def clean_comment(raw: str | None) -> str | None:
    """Recorta, quita caracteres de control y colapsa espacios. Vacío -> None."""
    if raw is None:
        return None
    text = _CONTROL_CHARS.sub("", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def classify_comment(comment: str | None) -> tuple[bool, str | None]:
    """(oculto?, motivo). Motivo: 'link' | 'service' | None."""
    if not comment:
        return False, None
    if _LINK_PATTERN.search(comment):
        return True, "link"
    if _SERVICE_PATTERN.search(_fold(comment)):
        return True, "service"
    return False, None


def display_name(first_name: str | None) -> str:
    """Solo el primer nombre; sin nombre, 'Cliente verificado'."""
    first = (first_name or "").strip().split(" ")[0]
    return first.capitalize() if first else "Cliente verificado"
