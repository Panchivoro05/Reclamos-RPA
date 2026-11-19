"""Notificaciones push por cada cambio de estado (con el notificador falso y con Expo simulado)."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import (
    CanalNotificacion,
    Dispositivo,
    EstadoNotificacion,
    Notificacion,
    ReclamoEvento,
)
from app.services.bot import EjecutorBotSimulado
from app.services.notificaciones import notificar_push
from app.services.push import ErrorEnvio, MensajePush, PushExpo, PushFalso, ResultadoPush
from app.worker import notificaciones as tarea
from tests.test_dispositivos import TOKEN, registrar
from tests.test_procesamiento import nuevo_reclamo, procesar, un_combo
from tests.utils import CLIENTE2

OTRO_TOKEN = "ExponentPushToken[otroCelular]"


def ultimo_evento(db: Session) -> ReclamoEvento:
    return db.scalars(select(ReclamoEvento).order_by(ReclamoEvento.id.desc()).limit(1)).one()


def notificar(evento_id: int, push: PushFalso) -> EstadoNotificacion:
    with SessionLocal() as session:
        return notificar_push(session, evento_id, push)


def registros(db: Session) -> list[tuple[EstadoNotificacion, int, str | None]]:
    db.expire_all()
    return [
        (n.estado, n.destinatarios, n.detalle)
        for n in db.scalars(select(Notificacion).order_by(Notificacion.id))
    ]


def test_cada_cambio_de_estado_encola_su_notificacion(
    client: TestClient, db: Session, datos: None, notificaciones_encoladas: list[int]
) -> None:
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))
    procesar(reclamo_id, EjecutorBotSimulado())

    eventos = db.scalars(
        select(ReclamoEvento.id).where(ReclamoEvento.reclamo_id == reclamo_id).order_by("id")
    ).all()
    assert notificaciones_encoladas == list(eventos)
    assert len(eventos) == 5  # recibido … resuelto


def test_envia_el_aviso_a_los_celulares_del_cliente(
    client: TestClient, db: Session, datos: None
) -> None:
    registrar(client)
    registrar(client, token=OTRO_TOKEN, plataforma="ios")
    registrar(client, CLIENTE2, token="ExponentPushToken[deOtroCliente]")
    nuevo_reclamo(client, items=un_combo(client))
    push = PushFalso()

    assert notificar(ultimo_evento(db).id, push) == EstadoNotificacion.ENVIADA

    assert [m.token for m in push.enviados] == [TOKEN, OTRO_TOKEN]
    mensaje = push.enviados[0]
    assert mensaje.titulo == "Recibimos tu reclamo · RC-2026-000001"
    assert mensaje.cuerpo.startswith("Recibimos tu reclamo.")
    assert mensaje.datos == {
        "codigo": "RC-2026-000001",
        "estado": "recibido",
        "url": "burgerya://reclamos/RC-2026-000001",
    }
    assert registros(db) == [(EstadoNotificacion.ENVIADA, 2, None)]


def test_no_se_envia_dos_veces_el_mismo_evento(
    client: TestClient, db: Session, datos: None
) -> None:
    registrar(client)
    nuevo_reclamo(client, items=un_combo(client))
    push = PushFalso()
    evento_id = ultimo_evento(db).id

    notificar(evento_id, push)
    assert notificar(evento_id, push) == EstadoNotificacion.OMITIDA
    assert len(push.enviados) == 1


def test_sin_celulares_registrados_se_omite(client: TestClient, db: Session, datos: None) -> None:
    nuevo_reclamo(client, items=un_combo(client))
    assert notificar(ultimo_evento(db).id, PushFalso()) == EstadoNotificacion.OMITIDA
    assert registros(db) == [(EstadoNotificacion.OMITIDA, 0, "Sin dispositivos")]


def test_celular_sin_la_app_se_desactiva(client: TestClient, db: Session, datos: None) -> None:
    registrar(client)
    registrar(client, token=OTRO_TOKEN)
    nuevo_reclamo(client, items=un_combo(client))
    push = PushFalso(errores={OTRO_TOKEN: "DeviceNotRegistered"})

    assert notificar(ultimo_evento(db).id, push) == EstadoNotificacion.ENVIADA

    db.expire_all()
    activos = {d.token: d.activo for d in db.scalars(select(Dispositivo))}
    assert activos == {TOKEN: True, OTRO_TOKEN: False}
    assert registros(db)[0][1] == 1


def test_si_expo_falla_se_libera_para_reintentar(
    client: TestClient, db: Session, datos: None
) -> None:
    class PushCaido(PushFalso):
        def enviar(self, mensajes: list[MensajePush]) -> list[ResultadoPush]:
            raise ErrorEnvio("Expo no responde")

    registrar(client)
    nuevo_reclamo(client, items=un_combo(client))
    evento_id = ultimo_evento(db).id

    with pytest.raises(ErrorEnvio):
        notificar(evento_id, PushCaido())
    assert registros(db) == []

    assert notificar(evento_id, PushFalso()) == EstadoNotificacion.ENVIADA


def test_la_tarea_reintenta_si_expo_falla(
    client: TestClient, db: Session, datos: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    class PushCaido(PushFalso):
        def enviar(self, mensajes: list[MensajePush]) -> list[ResultadoPush]:
            raise ErrorEnvio("Expo no responde")

    registrar(client)
    nuevo_reclamo(client, items=un_combo(client))
    monkeypatch.setattr(tarea, "get_notificador_push", PushCaido)
    reintentos: list[int] = []

    def _reintentar(**opciones: object) -> Exception:
        reintentos.append(int(str(opciones["countdown"])))
        return RuntimeError("reintento")

    monkeypatch.setattr(tarea.enviar_notificaciones, "retry", _reintentar)
    with pytest.raises(RuntimeError, match="reintento"):
        tarea.enviar_notificaciones.run(ultimo_evento(db).id)
    assert reintentos == [10]


def test_el_canal_queda_registrado(client: TestClient, db: Session, datos: None) -> None:
    registrar(client)
    nuevo_reclamo(client, items=un_combo(client))
    notificar(ultimo_evento(db).id, PushFalso())
    db.expire_all()
    assert db.scalars(select(Notificacion.canal)).all() == [CanalNotificacion.PUSH]


# ---------- Expo Push Service (HTTP simulado) ----------


def expo_simulado(responder: httpx.MockTransport) -> PushExpo:
    return PushExpo(
        "https://exp.host/--/api/v2/push/send", "secreto", httpx.Client(transport=responder)
    )


def test_expo_recibe_el_formato_esperado() -> None:
    pedidos: list[httpx.Request] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"status": "ok", "id": "1"},
                    {
                        "status": "error",
                        "message": "no registrado",
                        "details": {"error": "DeviceNotRegistered"},
                    },
                ]
            },
        )

    mensajes = [
        MensajePush(TOKEN, "Título", "Cuerpo", {"codigo": "RC-2026-000001"}),
        MensajePush(OTRO_TOKEN, "Título", "Cuerpo"),
    ]
    resultados = expo_simulado(httpx.MockTransport(responder)).enviar(mensajes)

    assert [(r.ok, r.token_invalido) for r in resultados] == [(True, False), (False, True)]
    cuerpo = json.loads(pedidos[0].content)
    assert cuerpo[0] == {
        "to": TOKEN,
        "title": "Título",
        "body": "Cuerpo",
        "data": {"codigo": "RC-2026-000001"},
        "sound": "default",
        "priority": "high",
        "channelId": "reclamos",
    }
    assert pedidos[0].headers["Authorization"] == "Bearer secreto"


def test_expo_caido_es_error_de_envio() -> None:
    push = expo_simulado(httpx.MockTransport(lambda _: httpx.Response(503)))
    with pytest.raises(ErrorEnvio):
        push.enviar([MensajePush(TOKEN, "t", "c")])


def test_expo_envia_en_lotes_de_100() -> None:
    lotes: list[int] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        cantidad = len(json.loads(pedido.content))
        lotes.append(cantidad)
        return httpx.Response(200, json={"data": [{"status": "ok"}] * cantidad})

    mensajes = [MensajePush(f"ExponentPushToken[{i}]", "t", "c") for i in range(150)]
    assert len(expo_simulado(httpx.MockTransport(responder)).enviar(mensajes)) == 150
    assert lotes == [100, 50]
