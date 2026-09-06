"""Regresiones del parseo de /products/agent-search.

El repo no tiene pytest instalado, asi que este archivo corre solo:
    python3 tests/test_agent_search.py
Tambien funciona bajo pytest si algun dia se anade.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
os.environ.setdefault("AGENT_API_KEY", "test")

from app.routers.products import (  # noqa: E402
    _console_matches,
    _split_agent_query,
    router,
)


def test_orden_de_rutas():
    """agent-* debe registrarse antes que /{id_product} o la ruta dinamica las captura."""
    rutas = [r.path for r in router.routes]
    dinamica = rutas.index("/products/{id_product}")
    assert rutas.index("/products/agent-search") < dinamica
    assert rutas.index("/products/agent-catalog") < dinamica


def test_la_plataforma_no_contamina_el_termino():
    """El bug que hace que /products/search devuelva 0 filas de productos que existen."""
    assert _split_agent_query("FC 27 para PS5") == ("fc27", ["playstation5"])
    assert _split_agent_query("FC 27") == ("fc27", [])


def test_plataformas_de_varias_palabras():
    """'series x' no debe dejar una 'x' suelta pegada al termino de busqueda."""
    assert _split_agent_query("cuanto vale gta 6 para xbox series x") == ("gta6", ["series"])
    assert _split_agent_query("play station 5 fc 26") == ("fc26", ["playstation5"])
    assert _split_agent_query("nintendo switch 2 mario") == ("mario", ["switch2"])


def test_varias_plataformas_a_la_vez():
    assert _split_agent_query("FC 27 para PS5 o Xbox") == ("fc27", ["playstation5", "xbox"])


def test_consulta_sin_producto_devuelve_termino_vacio():
    """Mejor pedir el nombre que buscar 'preciops5' y responder 'no disponible'."""
    assert _split_agent_query("precio ps5") == ("", ["playstation5"])


def test_saludos_y_ruido_se_descartan():
    assert _split_agent_query("hola buenas tienen hades 2") == ("hades2", [])


def test_console_matches():
    assert _console_matches("PlayStation 5", ["playstation5"])
    assert _console_matches("PS5", ["playstation5"])
    assert _console_matches("Xbox Series X", ["series"])
    assert _console_matches("Xbox Series X", ["xbox"])
    assert not _console_matches("Nintendo Switch", ["playstation5"])
    assert not _console_matches(None, ["xbox"])
    assert not _console_matches("PS5", [])


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if not nombre.startswith("test_"):
            continue
        try:
            fn()
            print(f"  OK    {nombre}")
        except AssertionError as e:
            fallos += 1
            print(f"  FALLA {nombre}: {e}")
    print(f"\n{'TODO OK' if not fallos else f'{fallos} fallo(s)'}")
    sys.exit(1 if fallos else 0)
