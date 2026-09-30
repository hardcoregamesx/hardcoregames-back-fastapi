"""Reglas de las reseñas de producto (filtro de temas, limpieza, rutas).

El repo no tiene pytest instalado, asi que este archivo corre solo:
    python3 tests/test_reviews.py
Tambien funciona bajo pytest si algun dia se anade.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
os.environ.setdefault("AGENT_API_KEY", "test")

from app.routers.reviews import ReviewIn, router  # noqa: E402
from app.services.reviews import MAX_COMMENT_LENGTH, classify_comment, clean_comment, display_name  # noqa: E402


def test_comentario_del_juego_se_muestra():
    for texto in (
        "Increible historia, los graficos son una locura",
        "Muy divertido para jugar en linea con amigos",
        "Se siente lento al principio pero mejora",  # 'lento' del juego, no del servicio
        "El mejor FC en años",
    ):
        assert classify_comment(texto) == (False, None), texto


def test_comentario_del_servicio_se_oculta_sea_bueno_o_malo():
    """Se filtra por tema, no por tono."""
    for texto in (
        "Excelente servicio, muy rapida la entrega",
        "La entrega se demoro muchisimo",
        "Pesima atención, nunca respondieron",
        "Me ayudaron por WhatsApp con la instalación",
        "Buena garantia y soporte",
        "TIENDA CONFIABLE",
        "Hardcore Games me atendió súper",
    ):
        oculto, motivo = classify_comment(texto)
        assert oculto and motivo == "service", texto


def test_enlaces_se_ocultan():
    assert classify_comment("compren aqui www.algo.com") == (True, "link")
    assert classify_comment("mira https://x.y/z") == (True, "link")


def test_sin_comentario_no_hay_nada_que_ocultar():
    assert classify_comment(None) == (False, None)
    assert classify_comment("") == (False, None)


def test_limpieza_de_comentarios():
    assert clean_comment(None) is None
    assert clean_comment("   \n\t ") is None
    assert clean_comment("  hola   mundo \n\n ok ") == "hola mundo ok"
    assert clean_comment("a\x00b\x07c") == "abc"


def test_nombre_visible():
    assert display_name("maría josé") == "María"
    assert display_name("  ") == "Cliente verificado"
    assert display_name(None) == "Cliente verificado"


def test_validacion_de_estrellas():
    for bien in (1, 3, 5):
        assert ReviewIn(rating=bien).rating == bien
    for mal in (0, 6, -1):
        try:
            ReviewIn(rating=mal)
        except Exception:
            continue
        raise AssertionError(f"rating {mal} deberia rechazarse")


def test_rutas_registradas():
    rutas = {(r.path, tuple(sorted(r.methods))) for r in router.routes}
    assert ("/reviews/mine", ("GET",)) in rutas
    assert ("/reviews/product/{product_id}", ("GET",)) in rutas
    assert ("/reviews/product/{product_id}", ("PUT",)) in rutas


def test_limite_del_comentario():
    assert MAX_COMMENT_LENGTH == 300


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {nombre}")
            except AssertionError as e:
                fallos += 1
                print(f"FAIL {nombre}: {e}")
    sys.exit(1 if fallos else 0)
