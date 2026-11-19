"""Mensajes de los hitos redactados por la IA: verificación de datos y respaldo con plantilla."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import EstadoReclamo, LlamadaIA, OperacionIA, ReclamoEvento, TipoReclamo
from app.services.bot import EjecutorBotSimulado
from app.services.ia import EntradaMensaje, ErrorIA, MensajeRedactado, ProveedorSimulado
from app.services.mensajes import motivo_de_rechazo
from app.services.procesamiento import Resultado, procesar_reclamo
from tests.test_ia_gemini import _proveedor, _respuesta
from tests.test_procesamiento import leer, nuevo_reclamo, un_combo

PLANTILLA = "¡Listo! Registramos un reembolso de S/ 27.90. Número de operación: CMP-000012."
OBLIGATORIOS = ["S/ 27.90", "CMP-000012"]


# ---------- Verificación (función pura) ----------


def test_mensaje_que_respeta_los_datos_se_acepta() -> None:
    texto = (
        "¡Gracias por tu paciencia! Ya registramos tu reembolso de S/ 27.90; "
        "tu número de operación es CMP-000012."
    )

    assert motivo_de_rechazo(texto, PLANTILLA, OBLIGATORIOS) is None


@pytest.mark.parametrize(
    ("texto", "motivo"),
    [
        ("Listo, reembolso hecho. Operación CMP-000012.", "falta S/ 27.90"),
        ("Registramos tu reembolso de S/27.90, operación CMP-000012.", "falta S/ 27.90"),
        (
            "Registramos S/ 27.90 (operación CMP-000012) y te regalamos S/ 10 extra.",
            "números que no están en la plantilla: 10",
        ),
        (
            "Registramos S/ 27.90, operación CMP-000012. Llegará en 48 horas.",
            "números que no están en la plantilla: 48",
        ),
        (
            "Nuestra inteligencia artificial aprobó S/ 27.90, operación CMP-000012.",
            "tema interno",
        ),
        (
            "Tras la revisión antifraude registramos S/ 27.90, operación CMP-000012.",
            "tema interno ('fraude')",
        ),
        (
            "Registramos S/ 27.90 (CMP-000012). Más info en https://burgerya.pe",
            "tema interno ('http')",
        ),
        ("Listo.", "largo fuera de rango"),
    ],
)
def test_mensaje_con_datos_inventados_o_internos_se_rechaza(texto: str, motivo: str) -> None:
    rechazo = motivo_de_rechazo(texto, PLANTILLA, OBLIGATORIOS)

    assert rechazo is not None
    assert motivo in rechazo


# ---------- En el procesamiento ----------


def _procesar(reclamo_id: int, ia: Any, bot: EjecutorBotSimulado | None = None) -> Resultado:
    with SessionLocal() as session:
        return procesar_reclamo(session, reclamo_id, bot or EjecutorBotSimulado(), ia=ia)


def _mensajes(reclamo_id: int) -> dict[str, str]:
    with SessionLocal() as session:
        eventos = session.scalars(
            select(ReclamoEvento).where(ReclamoEvento.reclamo_id == reclamo_id)
        )
        return {e.estado.value: e.mensaje for e in eventos}


def _redacciones(reclamo_id: int) -> list[LlamadaIA]:
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(LlamadaIA)
                .where(
                    LlamadaIA.reclamo_id == reclamo_id,
                    LlamadaIA.operacion == OperacionIA.REDACTAR_MENSAJE,
                )
                .order_by(LlamadaIA.id)
            )
        )


def test_la_ia_redacta_los_hitos_y_los_intermedios_quedan_fijos(
    client: TestClient, datos: None
) -> None:
    ia = ProveedorSimulado()
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))

    assert _procesar(reclamo_id, ia) == Resultado.RESUELTO

    mensajes = _mensajes(reclamo_id)
    assert mensajes["validado"].startswith("¡Buenas noticias! ¡Tu reclamo fue aprobado!")
    assert mensajes["resuelto"].startswith("¡Gracias por tu paciencia! ¡Listo!")
    assert "CMP-000001" in mensajes["resuelto"]
    assert mensajes["en_validacion"] == "Estamos revisando tu reclamo."
    assert [e.estado for e in ia.entradas_mensaje] == [
        EstadoReclamo.VALIDADO,
        EstadoReclamo.RESUELTO,
    ]
    assert all(r.exito for r in _redacciones(reclamo_id))


def test_monto_inventado_se_reemplaza_por_la_plantilla(client: TestClient, datos: None) -> None:
    def generoso(entrada: EntradaMensaje) -> MensajeRedactado:
        return MensajeRedactado(mensaje="¡Te devolvemos S/ 50.00 por las molestias!")

    reclamo_id = nuevo_reclamo(client, items=un_combo(client))

    assert _procesar(reclamo_id, ProveedorSimulado(mensaje=generoso)) == Resultado.RESUELTO

    mensajes = _mensajes(reclamo_id)
    assert (
        mensajes["validado"] == "¡Tu reclamo fue aprobado! Te corresponde un reembolso de S/ 27.90."
    )
    assert "S/ 50.00" not in json.dumps(mensajes, ensure_ascii=False)
    redacciones = _redacciones(reclamo_id)
    assert [r.exito for r in redacciones] == [False, False]
    assert "Mensaje rechazado: falta S/ 27.90" in str(redacciones[0].error)


def test_si_la_ia_no_redacta_el_reclamo_sigue_con_la_plantilla(
    client: TestClient, datos: None
) -> None:
    def caida(_: EntradaMensaje) -> MensajeRedactado:
        raise ErrorIA("503: alta demanda")

    reclamo_id = nuevo_reclamo(client, items=un_combo(client))

    assert _procesar(reclamo_id, ProveedorSimulado(mensaje=caida)) == Resultado.RESUELTO
    assert _mensajes(reclamo_id)["resuelto"].startswith("¡Listo! Registramos un reembolso")


def test_el_escalado_no_le_pasa_el_motivo_interno_a_la_ia(client: TestClient, datos: None) -> None:
    ia = ProveedorSimulado()
    reclamo_id = nuevo_reclamo(
        client, items=un_combo(client), descripcion="Me trajeron otra hamburguesa en vez del combo"
    )

    assert _procesar(reclamo_id, ia) == Resultado.ESCALADO

    entrada = ia.entradas_mensaje[-1]
    assert entrada.estado is EstadoReclamo.ESCALADO
    assert "IA" not in entrada.mensaje_base and "producto_equivocado" not in entrada.mensaje_base
    assert _mensajes(reclamo_id)["escalado"].startswith("Lamentamos el inconveniente.")
    assert "Según la IA" in str(leer(reclamo_id).motivo_escalamiento)  # solo para el agente


def test_gemini_redacta_con_tiempo_corto_y_sin_reintentos() -> None:
    respuesta = json.dumps({"mensaje": "¡Listo! Tu reembolso de S/ 27.90 ya está registrado."})
    proveedor, modelos = _proveedor(lambda: _respuesta(respuesta))
    entrada = EntradaMensaje(
        EstadoReclamo.RESUELTO,
        TipoReclamo.PEDIDO_INCOMPLETO,
        ["Combo Clásico"],
        "Mensaje base con S/ 27.90.",
    )

    redactado = proveedor.redactar_mensaje(entrada).resultado

    assert "S/ 27.90" in redactado.mensaje
    config = modelos.llamadas[0]["config"]
    assert config.http_options.timeout == 15_000
    assert config.http_options.retry_options.attempts == 1
    assert config.temperature == 0.5
    assert "Mensaje base: Mensaje base con S/ 27.90." in modelos.llamadas[0]["contents"]
