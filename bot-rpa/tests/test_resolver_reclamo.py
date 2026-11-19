"""Pruebas de punta a punta: el bot opera un SISCAJA real con un navegador real (oculto)."""

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from bot_rpa.config import Settings
from bot_rpa.ejecutar import ResultadoBot, SolicitudBot, resolver_reclamo

pytestmark = pytest.mark.e2e

ITEMS_301 = [{"producto": "Hamburguesa Clásica", "cantidad": 1}]


def resolver(ajustes: Settings, **datos: Any) -> ResultadoBot:
    base: dict[str, Any] = {
        "pedido": "BY-000301",
        "solucion": "reembolso_parcial",
        "monto": "10",
        "motivo": "Prueba automatica del bot RPA",
        "tipo_reclamo": "pedido_incompleto",
    }
    return resolver_reclamo(SolicitudBot(**{**base, **datos}), settings=ajustes)


def compensaciones(caja_db: sqlite3.Connection) -> list[sqlite3.Row]:
    return caja_db.execute("SELECT * FROM compensaciones ORDER BY id").fetchall()


def test_flujo_feliz_registra_la_compensacion_por_la_interfaz(
    ajustes: Settings, caja_db: sqlite3.Connection
) -> None:
    ajustes.grabar_video = True
    resultado = resolver(ajustes, items_esperados=ITEMS_301, total_esperado="46.30")

    assert resultado.exito, resultado.mensaje
    assert resultado.codigo_error is None
    assert resultado.numero_operacion == "CMP-000001"
    assert resultado.monto_registrado == "S/ 10.00"
    assert [p["paso"] for p in resultado.pasos] == [
        "login",
        "pedido",
        "verificacion",
        "formulario",
        "comprobante",
    ]

    # Evidencia: una captura por paso, el video y el resultado.json en la carpeta.
    carpeta = Path(resultado.carpeta)
    for paso in resultado.pasos:
        assert (carpeta / paso["captura"]).is_file()
    assert resultado.video == "video.webm"
    assert (carpeta / "video.webm").stat().st_size > 0
    guardado = json.loads((carpeta / "resultado.json").read_text(encoding="utf-8"))
    assert guardado["numero_operacion"] == "CMP-000001"
    assert guardado["total_en_caja"] == "S/ 46.30"

    # SISCAJA guardó exactamente lo que el bot escribió en el formulario.
    (fila,) = compensaciones(caja_db)
    assert fila["numero"] == "CMP-000001"
    assert fila["tipo"] == "reembolso_parcial"
    assert fila["monto_centimos"] == 1000
    assert fila["motivo"] == "Prueba automatica del bot RPA"


def test_pedido_inexistente(ajustes: Settings, caja_db: sqlite3.Connection) -> None:
    resultado = resolver(ajustes, pedido="BY-999999")

    assert not resultado.exito
    assert resultado.codigo_error == "pedido_inexistente"
    assert resultado.mensaje == "No existe el pedido BY-999999."
    assert [p["paso"] for p in resultado.pasos] == ["login", "error"]
    assert compensaciones(caja_db) == []


def test_monto_excedido_lo_rechaza_siscaja(ajustes: Settings, caja_db: sqlite3.Connection) -> None:
    resultado = resolver(ajustes, monto="46.31")

    assert not resultado.exito
    assert resultado.codigo_error == "compensacion_rechazada"
    assert resultado.mensaje == "Monto excedido: el maximo reembolsable es S/ 46.30."
    assert resultado.pasos[-1]["paso"] == "error"
    assert compensaciones(caja_db) == []


def test_items_que_no_coinciden_no_llegan_al_formulario(
    ajustes: Settings, caja_db: sqlite3.Connection
) -> None:
    resultado = resolver(
        ajustes, items_esperados=[{"producto": "Nuggets x6", "cantidad": 1}], total_esperado=""
    )

    assert resultado.codigo_error == "datos_no_coinciden"
    assert "Nuggets x6" in resultado.mensaje
    assert "formulario" not in [p["paso"] for p in resultado.pasos]
    assert compensaciones(caja_db) == []


def test_total_distinto_al_esperado(ajustes: Settings, caja_db: sqlite3.Connection) -> None:
    resultado = resolver(ajustes, total_esperado="50.00")

    assert resultado.codigo_error == "datos_no_coinciden"
    assert resultado.mensaje == "El total en caja es S/ 46.30 y el esperado S/ 50.00."
    assert compensaciones(caja_db) == []


def test_pedido_cancelado(ajustes: Settings, caja_db: sqlite3.Connection) -> None:
    resultado = resolver(ajustes, pedido="BY-000302", solucion="cupon", monto="5")

    assert resultado.codigo_error == "pedido_no_compensable"
    assert compensaciones(caja_db) == []


def test_credenciales_invalidas(ajustes: Settings, caja_db: sqlite3.Connection) -> None:
    ajustes.operador_clave = "clave-equivocada"
    resultado = resolver(ajustes)

    assert resultado.codigo_error == "credenciales_invalidas"
    assert resultado.mensaje == "Usuario o clave incorrectos."
    assert compensaciones(caja_db) == []


def test_siscaja_caido_termina_con_error_controlado(ajustes: Settings, tmp_path: Path) -> None:
    ajustes.caja_url = "http://127.0.0.1:1"
    resultado = resolver(ajustes)

    assert not resultado.exito
    assert resultado.codigo_error == "error_inesperado"
    assert (Path(resultado.carpeta) / "resultado.json").is_file()


def test_la_clave_no_queda_en_ninguna_salida(
    ajustes: Settings, caja_db: sqlite3.Connection
) -> None:
    resultado = resolver(ajustes, solucion="reenvio", monto="")
    assert resultado.exito, resultado.mensaje

    for archivo in Path(resultado.carpeta).rglob("*"):
        if archivo.is_file() and archivo.suffix in {".json", ".xml", ".html", ".txt", ".log"}:
            assert ajustes.operador_clave not in archivo.read_text(errors="ignore"), archivo


def test_un_reintento_no_compensa_dos_veces_el_mismo_reclamo(
    ajustes: Settings, caja_db: sqlite3.Connection
) -> None:
    primero = resolver(ajustes, reclamo="RC-2026-000123")
    assert primero.exito, primero.mensaje
    assert primero.numero_operacion == "CMP-000001"

    # El worker reintenta (por ejemplo, se cortó justo después de registrar).
    segundo = resolver(ajustes, reclamo="RC-2026-000123")

    assert segundo.exito, segundo.mensaje
    assert segundo.numero_operacion == "CMP-000001"
    assert segundo.monto_registrado == "S/ 10.00"
    assert segundo.datos["reutilizada"] == "si"
    assert "formulario" not in [p["paso"] for p in segundo.pasos]
    (fila,) = compensaciones(caja_db)
    assert fila["motivo"] == "RC-2026-000123 - Prueba automatica del bot RPA"

    # Otro reclamo del mismo pedido sí registra su propia compensación.
    otro = resolver(ajustes, reclamo="RC-2026-000124", solucion="cupon", monto="5")
    assert otro.numero_operacion == "CMP-000002"
