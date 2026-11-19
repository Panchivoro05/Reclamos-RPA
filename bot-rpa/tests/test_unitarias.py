"""Pruebas rápidas, sin navegador: validaciones, comparación de datos y armado del resultado."""

import json
from pathlib import Path

import pytest

from bot_rpa.BotRPA import BotRPA, ErrorBot, a_centimos
from bot_rpa.ejecutar import SolicitudBot


def test_solicitud_valida_codigo_y_solucion() -> None:
    SolicitudBot(pedido="BY-000101", solucion="cupon", motivo="x")
    with pytest.raises(ValueError, match="pedido"):
        SolicitudBot(pedido="101", solucion="cupon", motivo="x")
    with pytest.raises(ValueError, match="Solucion"):
        SolicitudBot(pedido="BY-000101", solucion="regalo", motivo="x")


def test_a_centimos() -> None:
    assert a_centimos("S/ 82.50") == 8250
    assert a_centimos("S/ 1,234.56") == 123456
    assert a_centimos("10") == 1000
    with pytest.raises(ValueError):
        a_centimos("abc")


def test_verificar_items_suma_filas_repetidas_e_ignora_mayusculas() -> None:
    bot = BotRPA()
    en_pantalla = [
        {"producto": "Papas Fritas", "cantidad": "1"},
        {"producto": "papas fritas", "cantidad": "1"},
    ]
    bot.verificar_items(en_pantalla, json.dumps([{"producto": "PAPAS FRITAS", "cantidad": 2}]))
    with pytest.raises(ErrorBot, match=r"\[datos_no_coinciden\].*3 x PAPAS FRITAS"):
        bot.verificar_items(en_pantalla, json.dumps([{"producto": "PAPAS FRITAS", "cantidad": 3}]))


def test_sin_datos_esperados_no_compara() -> None:
    bot = BotRPA()
    bot.verificar_items([], "")
    bot.verificar_total("S/ 10.00", "")


@pytest.mark.parametrize(
    ("estado", "mensaje", "exito", "codigo", "texto"),
    [
        ("PASS", "", True, None, "Compensacion registrada en SISCAJA."),
        (
            "FAIL",
            "[pedido_inexistente] No existe el pedido BY-1.",
            False,
            "pedido_inexistente",
            "No existe el pedido BY-1.",
        ),
        ("FAIL", "TimeoutError: algo raro", False, "error_inesperado", "TimeoutError: algo raro"),
    ],
)
def test_finalizar_resultado(
    tmp_path: Path, estado: str, mensaje: str, exito: bool, codigo: str | None, texto: str
) -> None:
    bot = BotRPA()
    bot.iniciar_resultado(str(tmp_path), pedido="BY-000101")
    bot.registrar_paso("login", "Inicio de sesion", str(tmp_path / "capturas" / "01_login"))

    datos = json.loads(Path(bot.finalizar_resultado(estado, mensaje)).read_text())

    assert datos["exito"] is exito
    assert datos["codigo_error"] == codigo
    assert datos["mensaje"] == texto
    assert datos["pedido"] == "BY-000101"
    assert datos["pasos"][0]["captura"] == "capturas/01_login.png"
    assert datos["video"] is None


def test_el_motivo_en_caja_empieza_con_el_codigo_del_reclamo() -> None:
    base = {"pedido": "BY-000101", "solucion": "cupon"}
    assert SolicitudBot(**base, motivo="Llegó tarde").motivo_en_caja == "Llegó tarde"
    con_codigo = SolicitudBot(**base, motivo="Llegó tarde", reclamo="RC-2026-000001")
    assert con_codigo.motivo_en_caja == "RC-2026-000001 - Llegó tarde"
    # Si el worker ya lo puso al inicio, no se repite.
    ya_tiene = SolicitudBot(**base, motivo="RC-2026-000001 - Llegó tarde", reclamo="RC-2026-000001")
    assert ya_tiene.motivo_en_caja == "RC-2026-000001 - Llegó tarde"
    with pytest.raises(ValueError, match="reclamo"):
        SolicitudBot(**base, motivo="x", reclamo="123")


def test_xpath_de_la_compensacion_previa_solo_acepta_codigos_validos() -> None:
    xpath = BotRPA().xpath_compensacion_de_reclamo("RC-2026-000001")
    assert xpath.startswith("xpath=(") and "'RC-2026-000001 '" in xpath
    with pytest.raises(ValueError):
        BotRPA().xpath_compensacion_de_reclamo("x') or ('1'='1")
