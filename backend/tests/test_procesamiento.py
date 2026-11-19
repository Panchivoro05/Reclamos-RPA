"""Flujo automático del reclamo con el bot simulado (sin navegador ni SISCAJA)."""

from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.tiempo import ahora_utc
from app.models import EjecucionBot, EstadoReclamo, Reclamo, SolucionCompensacion
from app.services.bot import EjecutorBotSimulado, ResultadoBot
from app.services.procesamiento import Resultado, procesar_reclamo, reclamos_sin_encolar
from app.worker import tareas
from tests.utils import crear_reclamo, item_id

EXITO = ResultadoBot(exito=True, codigo_error=None, mensaje="ok", numero_operacion="CMP-000077")
CAJA_CAIDA = ResultadoBot(exito=False, codigo_error="error_inesperado", mensaje="caja caida")
NO_COINCIDE = ResultadoBot(
    exito=False, codigo_error="datos_no_coinciden", mensaje="El pedido en caja no tiene: 1 x Combo."
)


def nuevo_reclamo(client: TestClient, **datos: Any) -> int:
    """Crea un reclamo por la API (queda en "recibido") y devuelve su id."""
    respuesta = crear_reclamo(client, **datos)
    assert respuesta.status_code == 201, respuesta.json()
    with SessionLocal() as session:
        return session.scalars(
            select(Reclamo.id).where(Reclamo.codigo == respuesta.json()["codigo"])
        ).one()


def un_combo(client: TestClient, cantidad: int = 1) -> list[dict[str, int]]:
    """Combo Clásico de BY-000101 (S/ 27.90 c/u)."""
    return [{"pedido_item_id": item_id(client, "BY-000101", 0), "cantidad_afectada": cantidad}]


def procesar(reclamo_id: int, ejecutor: EjecutorBotSimulado, **opciones: Any) -> Resultado:
    with SessionLocal() as session:
        return procesar_reclamo(session, reclamo_id, ejecutor, **opciones)


def leer(reclamo_id: int) -> Reclamo:
    with SessionLocal() as session:
        reclamo = session.get(Reclamo, reclamo_id)
        assert reclamo is not None
        _ = reclamo.eventos, reclamo.ejecuciones_bot  # carga antes de cerrar la sesión
        return reclamo


def linea_de_tiempo(reclamo: Reclamo) -> list[tuple[str, str]]:
    return [(e.estado.value, e.actor.value) for e in reclamo.eventos]


@pytest.fixture
def bot() -> EjecutorBotSimulado:
    return EjecutorBotSimulado()


# ---------- Camino feliz ----------


def test_reclamo_aprobado_lo_resuelve_el_bot(
    client: TestClient, datos: None, bot: EjecutorBotSimulado
) -> None:
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))

    assert procesar(reclamo_id, bot) == Resultado.RESUELTO

    reclamo = leer(reclamo_id)
    assert reclamo.estado == EstadoReclamo.RESUELTO
    assert reclamo.solucion == SolucionCompensacion.REEMBOLSO_PARCIAL
    assert reclamo.monto_compensacion == Decimal("27.90")
    assert reclamo.numero_operacion == "CMP-000001"
    assert reclamo.motivo_escalamiento is None
    assert linea_de_tiempo(reclamo) == [
        ("recibido", "cliente"),
        ("en_validacion", "sistema"),
        ("validado", "sistema"),
        ("en_resolucion", "bot"),
        ("resuelto", "bot"),
    ]
    assert reclamo.eventos[2].mensaje == (
        "¡Tu reclamo fue aprobado! Te corresponde un reembolso de S/ 27.90."
    )
    assert reclamo.eventos[-1].mensaje == (
        "¡Listo! Registramos un reembolso de S/ 27.90. Número de operación: CMP-000001."
    )
    (ejecucion,) = reclamo.ejecuciones_bot
    assert (ejecucion.intento, ejecucion.exito) == (1, True)


def test_el_bot_recibe_lo_que_debe_verificar_en_caja(
    client: TestClient, datos: None, bot: EjecutorBotSimulado
) -> None:
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))
    procesar(reclamo_id, bot)

    (solicitud,) = bot.solicitudes
    codigo = leer(reclamo_id).codigo
    assert solicitud.reclamo_codigo == codigo
    assert solicitud.pedido_codigo == "BY-000101"
    assert solicitud.solucion == SolucionCompensacion.REEMBOLSO_PARCIAL
    assert solicitud.monto == Decimal("27.90")
    assert solicitud.total_esperado == Decimal("82.50")
    assert solicitud.items_esperados == [
        {"producto": "Combo Clásico (hamburguesa + papas + gaseosa)", "cantidad": 1}
    ]
    # El código del reclamo viaja en el motivo: así el bot evita compensar dos veces.
    assert solicitud.motivo.startswith(f"{codigo} - Pedido incompleto: ")


def test_demora_recibe_un_cupon(client: TestClient, datos: None, bot: EjecutorBotSimulado) -> None:
    reclamo_id = nuevo_reclamo(client, pedido_codigo="BY-000104", tipo="demora", items=[])
    assert procesar(reclamo_id, bot) == Resultado.RESUELTO
    reclamo = leer(reclamo_id)
    assert (reclamo.solucion, reclamo.monto_compensacion) == (
        SolucionCompensacion.CUPON,
        Decimal("10.00"),
    )


# ---------- Escalamientos ----------


def test_monto_alto_se_escala_sin_llamar_al_bot(
    client: TestClient, datos: None, bot: EjecutorBotSimulado
) -> None:
    reclamo_id = nuevo_reclamo(client, items=un_combo(client, cantidad=2))  # S/ 55.80

    assert procesar(reclamo_id, bot) == Resultado.ESCALADO

    reclamo = leer(reclamo_id)
    assert bot.solicitudes == []
    assert reclamo.estado == EstadoReclamo.ESCALADO
    assert reclamo.motivo_escalamiento == "Supera el monto máximo automático: S/ 55.80 > S/ 40.00"
    assert linea_de_tiempo(reclamo) == [
        ("recibido", "cliente"),
        ("en_validacion", "sistema"),
        ("escalado", "sistema"),
    ]
    # El cliente ve un mensaje cordial, nunca el motivo interno.
    assert "Un agente de BurgerYa" in reclamo.eventos[-1].mensaje
    assert "S/ 55.80" not in reclamo.eventos[-1].mensaje


def test_cuarto_reclamo_del_mes_se_escala(
    client: TestClient, datos: None, bot: EjecutorBotSimulado
) -> None:
    nuevo_reclamo(client, pedido_codigo="BY-000101", tipo="demora", items=[])
    nuevo_reclamo(client, pedido_codigo="BY-000104", tipo="demora", items=[])
    nuevo_reclamo(
        client,
        pedido_codigo="BY-000104",
        tipo="pedido_incompleto",
        items=[{"pedido_item_id": item_id(client, "BY-000104", 0), "cantidad_afectada": 1}],
    )
    cuarto = nuevo_reclamo(client, items=un_combo(client))

    assert procesar(cuarto, bot) == Resultado.ESCALADO
    assert "ya tiene 3 reclamos" in str(leer(cuarto).motivo_escalamiento)


def test_error_de_negocio_del_bot_se_escala(client: TestClient, datos: None) -> None:
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))

    assert procesar(reclamo_id, EjecutorBotSimulado([NO_COINCIDE]), ultimo_intento=False) == (
        Resultado.ESCALADO  # no se reintenta: el dato no va a cambiar
    )

    reclamo = leer(reclamo_id)
    assert reclamo.motivo_escalamiento == (
        "El bot no pudo registrar la compensación (datos_no_coinciden): "
        "El pedido en caja no tiene: 1 x Combo."
    )
    assert [e.estado.value for e in reclamo.eventos][-2:] == ["en_resolucion", "escalado"]
    (ejecucion,) = reclamo.ejecuciones_bot
    assert ejecucion.codigo_error == "datos_no_coinciden"


# ---------- Reintentos e idempotencia ----------


def test_error_tecnico_se_reintenta_y_luego_resuelve(client: TestClient, datos: None) -> None:
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))
    bot = EjecutorBotSimulado([CAJA_CAIDA, EXITO])

    assert procesar(reclamo_id, bot, intento=1, ultimo_intento=False) == Resultado.REINTENTAR
    assert leer(reclamo_id).estado == EstadoReclamo.EN_RESOLUCION

    assert procesar(reclamo_id, bot, intento=2, ultimo_intento=False) == Resultado.RESUELTO

    reclamo = leer(reclamo_id)
    assert reclamo.numero_operacion == "CMP-000077"
    # El cliente no ve el fallo intermedio ni eventos repetidos.
    assert [e.estado.value for e in reclamo.eventos].count("en_resolucion") == 1
    assert [(e.intento, e.exito) for e in reclamo.ejecuciones_bot] == [(1, False), (2, True)]


def test_error_tecnico_en_el_ultimo_intento_se_escala(client: TestClient, datos: None) -> None:
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))
    resultado = procesar(reclamo_id, EjecutorBotSimulado([CAJA_CAIDA]), ultimo_intento=True)
    assert resultado == Resultado.ESCALADO
    assert "(error_inesperado)" in str(leer(reclamo_id).motivo_escalamiento)


def test_procesar_dos_veces_no_repite_nada(
    client: TestClient, datos: None, bot: EjecutorBotSimulado
) -> None:
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))
    assert procesar(reclamo_id, bot) == Resultado.RESUELTO
    assert procesar(reclamo_id, bot) == Resultado.SIN_CAMBIOS
    assert len(bot.solicitudes) == 1
    assert len(leer(reclamo_id).eventos) == 5


def test_retoma_desde_el_estado_en_que_quedo(
    client: TestClient, datos: None, db: Session, bot: EjecutorBotSimulado
) -> None:
    """Si el worker se cortó después de validar, sigue desde ahí sin validar de nuevo."""
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))
    reclamo = db.get(Reclamo, reclamo_id)
    assert reclamo is not None
    reclamo.estado = EstadoReclamo.VALIDADO
    reclamo.solucion = SolucionCompensacion.REEMBOLSO_PARCIAL
    reclamo.monto_compensacion = Decimal("27.90")
    db.commit()

    assert procesar(reclamo_id, bot) == Resultado.RESUELTO
    estados = [e.estado.value for e in leer(reclamo_id).eventos]
    assert estados == ["recibido", "en_resolucion", "resuelto"]


def test_reclamo_inexistente_no_hace_nada(bot: EjecutorBotSimulado) -> None:
    assert procesar(999_999, bot) == Resultado.SIN_CAMBIOS


def test_rescata_solo_los_recibido_que_llevan_tiempo_esperando(
    client: TestClient, datos: None, db: Session, bot: EjecutorBotSimulado
) -> None:
    resuelto = nuevo_reclamo(client, items=un_combo(client))
    procesar(resuelto, bot)
    olvidado = nuevo_reclamo(client, pedido_codigo="BY-000104", tipo="demora", items=[])
    reciente = nuevo_reclamo(client, pedido_codigo="BY-000101", tipo="demora", items=[])
    reclamo = db.get(Reclamo, olvidado)
    assert reclamo is not None
    reclamo.creado_en = ahora_utc() - timedelta(minutes=5)
    db.commit()

    with SessionLocal() as session:
        assert reclamos_sin_encolar(session, timedelta(minutes=2)) == [olvidado]
        assert reclamos_sin_encolar(session, timedelta(0)) == [olvidado, reciente]


def test_tarea_periodica_encola_los_olvidados(
    client: TestClient, datos: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    olvidado = nuevo_reclamo(client, pedido_codigo="BY-000104", tipo="demora", items=[])
    enviados: list[int] = []
    monkeypatch.setattr(tareas.procesar_reclamo_tarea, "delay", enviados.append)

    assert tareas.reencolar_sin_encolar.apply(args=[0]).get() == 1
    assert enviados == [olvidado]


# ---------- Cola y tarea de Celery ----------


def test_crear_un_reclamo_lo_encola(client: TestClient, datos: None, encolados: list[int]) -> None:
    reclamo_id = nuevo_reclamo(client)
    assert encolados == [reclamo_id]


def test_si_la_cola_falla_el_reclamo_igual_se_registra(
    client: TestClient, datos: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def valkey_caido(_: int) -> None:
        raise ConnectionError("Valkey no responde")

    monkeypatch.setattr("app.services.cola._enviar", valkey_caido)
    reclamo_id = nuevo_reclamo(client)
    assert leer(reclamo_id).estado == EstadoReclamo.RECIBIDO


def test_tarea_de_celery_reintenta_y_resuelve(
    client: TestClient,
    datos: None,
    monkeypatch: pytest.MonkeyPatch,
    configurar: Callable[..., None],
) -> None:
    configurar(worker_espera_reintento_s=0)
    bot = EjecutorBotSimulado([CAJA_CAIDA, EXITO])
    monkeypatch.setattr(tareas, "obtener_ejecutor", lambda: bot)
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))

    # apply() ejecuta la tarea aquí mismo (sin Valkey), reintentos incluidos.
    resultado = tareas.procesar_reclamo_tarea.apply(args=[reclamo_id])

    assert resultado.get() == "resuelto"
    reclamo = leer(reclamo_id)
    assert reclamo.estado == EstadoReclamo.RESUELTO
    assert [e.intento for e in reclamo.ejecuciones_bot] == [1, 2]


def test_tarea_escala_al_agotar_los_reintentos(
    client: TestClient,
    datos: None,
    monkeypatch: pytest.MonkeyPatch,
    configurar: Callable[..., None],
) -> None:
    configurar(worker_espera_reintento_s=0, worker_reintentos=2)
    bot = EjecutorBotSimulado(lambda _: CAJA_CAIDA)
    monkeypatch.setattr(tareas, "obtener_ejecutor", lambda: bot)
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))

    assert tareas.procesar_reclamo_tarea.apply(args=[reclamo_id]).get() == "escalado"
    assert len(bot.solicitudes) == 3  # intento original + 2 reintentos
    with SessionLocal() as session:
        intentos = session.scalars(
            select(EjecucionBot.intento).where(EjecucionBot.reclamo_id == reclamo_id)
        ).all()
    assert intentos == [1, 2, 3]
