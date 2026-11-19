import logging

from app.models import Reclamo

logger = logging.getLogger(__name__)


def _enviar(reclamo_id: int) -> None:
    # Import diferido: la API no carga Celery hasta que hace falta.
    from app.worker.tareas import procesar_reclamo_tarea

    procesar_reclamo_tarea.apply_async(
        args=[reclamo_id],
        # Si Valkey no responde, se rinde rápido: el reclamo ya está guardado.
        retry=True,
        retry_policy={"max_retries": 2, "interval_start": 0, "interval_step": 0.5},
    )


def encolar_reclamo(reclamo: Reclamo) -> bool:
    """Envía el reclamo al worker (Celery + Valkey). Devuelve False si la cola no respondió.

    Si falla, el reclamo igual queda registrado en "recibido": el worker lo retoma al arrancar
    (ver app.worker.tareas.reencolar_pendientes). El cliente nunca pierde su reclamo.
    """
    try:
        _enviar(reclamo.id)
    except Exception:
        logger.exception("No se pudo encolar el reclamo %s; quedará pendiente", reclamo.codigo)
        return False
    logger.info("Reclamo %s encolado (id=%s)", reclamo.codigo, reclamo.id)
    return True
