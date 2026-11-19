"""WebSocket /api/v1/ws: autenticación, reenvío de los eventos del cliente y fallas."""

import asyncio
import queue
import time
from collections import defaultdict
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.api import tiempo_real
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.main import app
from app.models import Cliente, EstadoReclamo
from app.services import eventos
from app.services.eventos import CambioEstado, canal_cliente, publicar_cambio
from app.services.suscripciones import SuscriptorValkey, get_suscriptor
from tests.test_procesamiento import nuevo_reclamo, un_combo

AUT_CLIENTE1 = {"tipo": "autenticar", "encabezados": {"X-Dev-User": "cliente1@burgerya.pe"}}
AUT_CLIENTE2 = {"tipo": "autenticar", "encabezados": {"X-Dev-User": "cliente2@burgerya.pe"}}


class BrokerMemoria:
    """Hace de Valkey: lo que se publica (desde cualquier hilo) llega a los suscritos."""

    def __init__(self) -> None:
        self.suscritos: dict[str, list[queue.Queue[str]]] = defaultdict(list)

    def publicar(self, canal: str, mensaje: str) -> None:
        for cola in list(self.suscritos[canal]):
            cola.put(mensaje)

    @asynccontextmanager
    async def escuchar(self, canal: str) -> AsyncIterator[AsyncIterator[str]]:
        cola: queue.Queue[str] = queue.Queue()
        self.suscritos[canal].append(cola)
        try:
            yield self._mensajes(cola)
        finally:
            self.suscritos[canal].remove(cola)

    async def _mensajes(self, cola: queue.Queue[str]) -> AsyncIterator[str]:
        while True:
            try:
                yield cola.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.01)


@pytest.fixture
def broker(monkeypatch: pytest.MonkeyPatch) -> Iterator[BrokerMemoria]:
    broker = BrokerMemoria()
    monkeypatch.setattr(eventos, "_publicar", broker.publicar)
    app.dependency_overrides[get_suscriptor] = lambda: broker
    yield broker
    app.dependency_overrides.pop(get_suscriptor, None)


def id_cliente(email: str) -> int:
    with SessionLocal() as session:
        return session.scalars(select(Cliente.id).where(Cliente.email == email)).one()


def cambio(cliente_id: int, codigo: str) -> CambioEstado:
    return CambioEstado(cliente_id, codigo, EstadoReclamo.RESUELTO, 1, datetime.now(UTC))


def test_recibe_en_vivo_los_cambios_de_sus_reclamos(
    client: TestClient, datos: None, broker: BrokerMemoria
) -> None:
    with client.websocket_connect("/api/v1/ws") as ws:
        ws.send_json(AUT_CLIENTE1)
        assert ws.receive_json() == {"tipo": "conectado"}

        nuevo_reclamo(client, items=un_combo(client))

        mensaje = ws.receive_json()
        assert mensaje["tipo"] == "reclamo_actualizado"
        assert (mensaje["codigo"], mensaje["estado"]) == ("RC-2026-000001", "recibido")


def test_no_recibe_los_de_otro_cliente(
    client: TestClient, datos: None, broker: BrokerMemoria
) -> None:
    with client.websocket_connect("/api/v1/ws") as ws:
        ws.send_json(AUT_CLIENTE2)
        assert ws.receive_json() == {"tipo": "conectado"}

        publicar_cambio(cambio(id_cliente("cliente1@burgerya.pe"), "RC-2026-000001"))
        publicar_cambio(cambio(id_cliente("cliente2@burgerya.pe"), "RC-2026-000002"))

        assert ws.receive_json()["codigo"] == "RC-2026-000002"


def test_responde_ping(client: TestClient, datos: None, broker: BrokerMemoria) -> None:
    with client.websocket_connect("/api/v1/ws") as ws:
        ws.send_json(AUT_CLIENTE1)
        ws.receive_json()
        ws.send_json({"tipo": "ping"})
        assert ws.receive_json() == {"tipo": "pong"}


def test_al_desconectarse_deja_de_escuchar(
    client: TestClient, datos: None, broker: BrokerMemoria
) -> None:
    canal = canal_cliente(id_cliente("cliente1@burgerya.pe"))
    with client.websocket_connect("/api/v1/ws") as ws:
        ws.send_json(AUT_CLIENTE1)
        ws.receive_json()
        assert len(broker.suscritos[canal]) == 1
    for _ in range(100):
        if not broker.suscritos[canal]:
            break
        time.sleep(0.01)
    assert broker.suscritos[canal] == []


@pytest.mark.parametrize(
    "primer_mensaje",
    [
        {"tipo": "autenticar", "encabezados": {}},
        {"tipo": "autenticar", "encabezados": {"X-Dev-User": "nadie@burgerya.pe"}},
        {"tipo": "ping"},
        ["no", "es", "un", "objeto"],
    ],
)
def test_sin_autenticacion_valida_se_cierra_con_4401(
    client: TestClient, datos: None, broker: BrokerMemoria, primer_mensaje: object
) -> None:
    with client.websocket_connect("/api/v1/ws") as ws:
        ws.send_json(primer_mensaje)
        with pytest.raises(WebSocketDisconnect) as cierre:
            ws.receive_json()
    assert cierre.value.code == 4401


def test_si_no_se_autentica_a_tiempo_se_cierra(
    client: TestClient, broker: BrokerMemoria, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tiempo_real, "ESPERA_AUTENTICACION_S", 0.1)
    with client.websocket_connect("/api/v1/ws") as ws, pytest.raises(WebSocketDisconnect) as cierre:
        ws.receive_json()
    assert cierre.value.code == 4401


def test_si_valkey_no_responde_se_cierra_con_1011(client: TestClient, datos: None) -> None:
    class SuscriptorCaido:
        @asynccontextmanager
        async def escuchar(self, canal: str) -> AsyncIterator[AsyncIterator[str]]:
            raise ConnectionError("Valkey no responde")
            yield  # pragma: no cover

    app.dependency_overrides[get_suscriptor] = SuscriptorCaido
    try:
        with client.websocket_connect("/api/v1/ws") as ws:
            ws.send_json(AUT_CLIENTE1)
            with pytest.raises(WebSocketDisconnect) as cierre:
                ws.receive_json()
        assert cierre.value.code == 1011
    finally:
        app.dependency_overrides.pop(get_suscriptor, None)


# ---------- Contra Valkey de verdad (se salta si no está corriendo) ----------


def _valkey_disponible() -> bool:
    try:
        return bool(redis.Redis.from_url(get_settings().valkey_url, socket_timeout=0.5).ping())
    except redis.RedisError:
        return False


@pytest.mark.skipif(not _valkey_disponible(), reason="Valkey no está corriendo")
def test_suscriptor_valkey_recibe_lo_publicado() -> None:
    url = get_settings().valkey_url
    canal = f"reclamos:prueba:{datetime.now(UTC).timestamp()}"

    async def escenario() -> str:
        async with SuscriptorValkey(url).escuchar(canal) as mensajes:
            await asyncio.sleep(0.1)  # que la suscripción quede activa en Valkey
            redis.Redis.from_url(url).publish(canal, '{"tipo": "hola"}')
            return await asyncio.wait_for(anext(mensajes), timeout=2)

    assert asyncio.run(escenario()) == '{"tipo": "hola"}'
