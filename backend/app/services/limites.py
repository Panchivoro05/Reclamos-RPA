"""Límite de consultas al asistente por cliente: cada consulta cuesta una llamada a la IA.

Se cuenta en Valkey (una clave por cliente y minuto que expira sola), así el límite vale
aunque la API corra en varios procesos. Si Valkey no responde, no se bloquea al cliente.
"""

import logging
import time

from app.core.errores import DemasiadasPeticiones
from app.services.eventos import _cliente_valkey

logger = logging.getLogger(__name__)

CONSULTAS_POR_MINUTO = 10


def _incrementar(clave: str) -> int:
    """Suma 1 al contador de la clave (que expira sola) y devuelve el total."""
    valkey = _cliente_valkey()
    cantidad = int(valkey.incr(clave))
    if cantidad == 1:
        valkey.expire(clave, 120)
    return cantidad


def controlar_consultas_asistente(cliente_id: int) -> None:
    clave = f"asistente:{cliente_id}:{int(time.time() // 60)}"
    try:
        cantidad = _incrementar(clave)
    except Exception:
        logger.warning("No se pudo contar la consulta al asistente (Valkey)")
        return
    if cantidad > CONSULTAS_POR_MINUTO:
        raise DemasiadasPeticiones(
            "demasiadas_consultas",
            "Hiciste muchas consultas seguidas. Espera un minuto e inténtalo de nuevo.",
        )
