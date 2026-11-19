"""Aviso de cada cambio de estado de un reclamo: en vivo (Valkey pub/sub) y notificaciones.

Quien cambia el estado (la API al crear el reclamo, el worker al procesarlo) llama a
`publicar_cambio` DESPUÉS del commit: así nadie avisa de algo que todavía no está guardado.
La API escucha el canal del cliente y reenvía el aviso a la app por WebSocket.

El aviso es pequeño (código y estado): la app vuelve a pedir el detalle por REST, que sigue
siendo la fuente de verdad. Si Valkey no responde, el aviso se pierde sin romper nada: el
cambio ya está en PostgreSQL y la app lo verá en su siguiente consulta.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

import redis

from app.core.config import get_settings
from app.models import EstadoReclamo, Reclamo, ReclamoEvento

logger = logging.getLogger(__name__)

TIPO_RECLAMO_ACTUALIZADO = "reclamo_actualizado"


@dataclass(frozen=True)
class CambioEstado:
    cliente_id: int
    reclamo_codigo: str
    estado: EstadoReclamo
    evento_id: int
    momento: datetime

    @classmethod
    def desde_evento(cls, reclamo: Reclamo, evento: ReclamoEvento) -> "CambioEstado":
        return cls(
            cliente_id=reclamo.cliente_id,
            reclamo_codigo=reclamo.codigo,
            estado=evento.estado,
            evento_id=evento.id,
            momento=evento.creado_en,
        )

    def mensaje(self) -> dict[str, Any]:
        """Lo que recibe la app por WebSocket."""
        return {
            "tipo": TIPO_RECLAMO_ACTUALIZADO,
            "codigo": self.reclamo_codigo,
            "estado": self.estado.value,
            "evento_id": self.evento_id,
            "momento": self.momento.isoformat(),
        }


def canal_cliente(cliente_id: int) -> str:
    """Un canal por cliente: recibe los cambios de todos sus reclamos (lista y detalle)."""
    return f"reclamos:cliente:{cliente_id}"


@lru_cache
def _cliente_valkey() -> redis.Redis:
    # Tiempos cortos: si Valkey está caído, la API y el worker siguen sin quedarse esperando.
    return redis.Redis.from_url(
        get_settings().valkey_url, socket_connect_timeout=0.5, socket_timeout=0.5
    )


def _publicar(canal: str, mensaje: str) -> None:
    _cliente_valkey().publish(canal, mensaje)


def _encolar_notificacion(evento_id: int) -> None:
    # Import diferido: la API no carga Celery hasta que hace falta.
    from app.worker.notificaciones import enviar_notificaciones

    enviar_notificaciones.apply_async(
        args=[evento_id],
        retry=True,
        retry_policy={"max_retries": 1, "interval_start": 0, "interval_step": 0.5},
    )


def publicar_cambio(cambio: CambioEstado) -> bool:
    """Avisa el cambio a la app (pub/sub) y encola sus notificaciones (push).

    Devuelve False si algo no llegó a Valkey. En ese caso el aviso o la notificación se
    pierden, pero el cambio ya está guardado: el cliente lo verá al abrir la app.
    """
    ok = True
    try:
        _publicar(canal_cliente(cambio.cliente_id), json.dumps(cambio.mensaje()))
    except Exception:
        ok = False
        logger.warning("No se pudo publicar el cambio de %s (Valkey)", cambio.reclamo_codigo)
    try:
        _encolar_notificacion(cambio.evento_id)
    except Exception:
        ok = False
        logger.warning("No se pudo encolar la notificación de %s", cambio.reclamo_codigo)
    return ok
