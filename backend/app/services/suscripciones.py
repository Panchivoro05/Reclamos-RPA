"""Escucha los canales de Valkey donde se publican los cambios de estado (ver eventos.py).

Cada conexión WebSocket abre su propia suscripción al canal de su cliente. Para el volumen
de este proyecto basta; con miles de conexiones se usaría una sola suscripción por proceso
que reparta los mensajes.
"""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol

import redis.asyncio as redis_async

from app.core.config import get_settings


class SuscriptorEventos(Protocol):
    def escuchar(self, canal: str) -> AbstractAsyncContextManager[AsyncIterator[str]]:
        """Suscribe al canal y entrega sus mensajes (texto JSON) mientras dure el contexto."""
        ...


class SuscriptorValkey:
    def __init__(self, url: str) -> None:
        self.url = url

    @asynccontextmanager
    async def escuchar(self, canal: str) -> AsyncIterator[AsyncIterator[str]]:
        # Sin socket_timeout: la suscripción espera mensajes sin límite. El health check
        # detecta si Valkey se cayó y corta la escucha con un error de conexión.
        cliente = redis_async.Redis.from_url(
            self.url, socket_connect_timeout=2, health_check_interval=30
        )
        pubsub = cliente.pubsub(ignore_subscribe_messages=True)
        try:
            await pubsub.subscribe(canal)
            yield _mensajes(pubsub)
        finally:
            await pubsub.aclose()
            await cliente.aclose()


async def _mensajes(pubsub: redis_async.client.PubSub) -> AsyncIterator[str]:
    async for mensaje in pubsub.listen():
        if mensaje["type"] == "message":
            datos = mensaje["data"]
            yield datos.decode() if isinstance(datos, bytes) else str(datos)


def get_suscriptor() -> SuscriptorEventos:
    """Dependencia de FastAPI (las pruebas la reemplazan por un suscriptor en memoria)."""
    return SuscriptorValkey(get_settings().valkey_url)
