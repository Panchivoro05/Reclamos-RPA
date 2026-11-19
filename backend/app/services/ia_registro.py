"""Registro de cada llamada a la IA (tabla `llamadas_ia`): latencia, tokens y costo aproximado.

`llamar` envuelve cualquier operación del proveedor: mide cuánto tardó, calcula el costo y deja
una fila, también cuando falla. La fila se agrega a la sesión del que llama (que decide cuándo
hacer commit), así queda en la misma transacción que la decisión tomada con ese resultado.
"""

import logging
import time
from collections.abc import Callable
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import LlamadaIA, OperacionIA
from app.services.ia import ErrorIA, RespuestaIA

logger = logging.getLogger(__name__)

UN_MILLON = Decimal(1_000_000)


def costo_usd(tokens_entrada: int, tokens_salida: int) -> Decimal:
    """Costo aproximado según los precios configurados (USD por millón de tokens)."""
    settings = get_settings()
    entrada = Decimal(str(settings.ia_precio_entrada_usd_millon))
    salida = Decimal(str(settings.ia_precio_salida_usd_millon))
    costo = (tokens_entrada * entrada + tokens_salida * salida) / UN_MILLON
    return costo.quantize(Decimal("0.000001"))


def llamar[T: BaseModel](
    session: Session,
    operacion: OperacionIA,
    proveedor: str,
    ejecutar: Callable[[], RespuestaIA[T]],
    *,
    reclamo_id: int | None = None,
) -> T:
    """Ejecuta la llamada, la registra y devuelve el resultado. Si falla, registra y relanza."""
    inicio = time.perf_counter()
    try:
        respuesta = ejecutar()
    except ErrorIA as error:
        session.add(
            LlamadaIA(
                reclamo_id=reclamo_id,
                operacion=operacion,
                proveedor=proveedor,
                modelo="",
                exito=False,
                error=str(error)[:2000],
                latencia_ms=_ms_desde(inicio),
            )
        )
        session.flush()
        logger.warning("IA %s falló: %s", operacion.value, error)
        raise

    uso = respuesta.uso
    latencia = _ms_desde(inicio)
    session.add(
        LlamadaIA(
            reclamo_id=reclamo_id,
            operacion=operacion,
            proveedor=proveedor,
            modelo=uso.modelo,
            exito=True,
            tokens_entrada=uso.tokens_entrada,
            tokens_salida=uso.tokens_salida,
            latencia_ms=latencia,
            costo_usd=costo_usd(uso.tokens_entrada, uso.tokens_salida),
            resultado=respuesta.resultado.model_dump(mode="json"),
        )
    )
    session.flush()
    logger.info("IA %s: %d ms (%s)", operacion.value, latencia, uso.modelo)
    return respuesta.resultado


def _ms_desde(inicio: float) -> int:
    return round((time.perf_counter() - inicio) * 1000)
