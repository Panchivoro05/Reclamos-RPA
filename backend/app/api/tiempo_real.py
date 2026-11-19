"""WebSocket con los cambios de estado de los reclamos del cliente, en vivo.

Protocolo (todos los mensajes son JSON con un campo "tipo"):

1. La app se conecta a /api/v1/ws y, en los primeros segundos, envía
   {"tipo": "autenticar", "encabezados": {"X-Dev-User": ...} o {"Authorization": ...}}.
   Son los mismos encabezados de las peticiones HTTP. Van en un mensaje y no en la URL para
   que el token no quede en los logs, y porque el WebSocket del navegador no admite
   encabezados (lo usará el panel web).
2. El servidor responde {"tipo": "conectado"}. Al recibirlo, la app recarga sus datos: así no
   se pierde nada de lo que pasó mientras estaba desconectada.
3. Por cada cambio llega {"tipo": "reclamo_actualizado", "codigo", "estado", ...}.
4. La app puede enviar {"tipo": "ping"} y recibe {"tipo": "pong"} (comprueba la conexión).

Si la autenticación falla se cierra con el código 4401; si Valkey no responde, con 1011
(la app vuelve a intentar y, mientras tanto, consulta cada pocos segundos).
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.api.deps import autenticar
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errores import ErrorAPI, NoAutenticado
from app.services.eventos import canal_cliente
from app.services.suscripciones import SuscriptorEventos, get_suscriptor

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tiempo real"])

ESPERA_AUTENTICACION_S = 10
CIERRE_NO_AUTENTICADO = 4401
CIERRE_ERROR_INTERNO = 1011


@router.websocket("/ws")
async def eventos_en_vivo(
    websocket: WebSocket,
    suscriptor: Annotated[SuscriptorEventos, Depends(get_suscriptor)],
) -> None:
    await websocket.accept()
    try:
        primer_mensaje = await asyncio.wait_for(
            websocket.receive_json(), timeout=ESPERA_AUTENTICACION_S
        )
        cliente_id = await run_in_threadpool(_cliente_del_mensaje, primer_mensaje)
    except WebSocketDisconnect:
        return
    except (TimeoutError, ValueError, ErrorAPI) as error:
        motivo = error.mensaje if isinstance(error, ErrorAPI) else "Autenticación inválida."
        await websocket.close(code=CIERRE_NO_AUTENTICADO, reason=motivo[:120])
        return

    try:
        async with suscriptor.escuchar(canal_cliente(cliente_id)) as mensajes:
            await websocket.send_json({"tipo": "conectado"})
            await _atender(websocket, mensajes)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.warning("Se cortó la escucha de eventos del cliente %s", cliente_id, exc_info=True)
        await _cerrar_sin_error(websocket, CIERRE_ERROR_INTERNO)


def _cliente_del_mensaje(mensaje: Any) -> int:
    if not isinstance(mensaje, dict) or mensaje.get("tipo") != "autenticar":
        raise NoAutenticado("sin_sesion", 'El primer mensaje debe ser {"tipo": "autenticar"}.')
    encabezados = {str(k).lower(): str(v) for k, v in (mensaje.get("encabezados") or {}).items()}
    with SessionLocal() as db:
        cliente = autenticar(
            db, get_settings(), encabezados.get("x-dev-user"), encabezados.get("authorization")
        )
        return cliente.id


async def _atender(websocket: WebSocket, mensajes: AsyncIterator[str]) -> None:
    """Reenvía los eventos y responde los ping a la vez. Termina cuando la app se desconecta
    o cuando se corta la suscripción (en ese caso relanza el error para cerrar con 1011)."""
    error_suscripcion: Exception | None = None

    async with anyio.create_task_group() as grupo:

        async def reenviar() -> None:
            nonlocal error_suscripcion
            try:
                async for mensaje in mensajes:
                    await websocket.send_text(mensaje)
                error_suscripcion = ConnectionError("La suscripción terminó.")
            except WebSocketDisconnect:
                pass
            except Exception as error:
                error_suscripcion = error
            grupo.cancel_scope.cancel()

        async def escuchar_app() -> None:
            try:
                while True:
                    tipo = _tipo_de(await websocket.receive_text())
                    if tipo == "ping":
                        await websocket.send_json({"tipo": "pong"})
            except WebSocketDisconnect:
                grupo.cancel_scope.cancel()

        grupo.start_soon(reenviar)
        grupo.start_soon(escuchar_app)

    if error_suscripcion is not None:
        raise error_suscripcion


def _tipo_de(texto: str) -> object:
    try:
        datos = json.loads(texto)
    except ValueError:
        return None
    return datos.get("tipo") if isinstance(datos, dict) else None


async def _cerrar_sin_error(websocket: WebSocket, codigo: int) -> None:
    with contextlib.suppress(RuntimeError):  # ya estaba cerrado
        await websocket.close(code=codigo)
