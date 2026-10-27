import logging

from app.models import Reclamo

logger = logging.getLogger(__name__)


def encolar_reclamo(reclamo: Reclamo) -> None:
    """Envía el reclamo al procesamiento automático.

    Por ahora solo lo registra en el log; en la fase 3 lo enviará a Celery (broker Valkey).
    """
    logger.info("Reclamo %s encolado para procesamiento (id=%s)", reclamo.codigo, reclamo.id)
