import logging
from datetime import timedelta

from celery import Task
from celery.signals import worker_ready

from app.core.config import BotModo, get_settings
from app.core.db import SessionLocal
from app.services.bot import EjecutorBot, EjecutorBotSimulado
from app.services.procesamiento import Resultado, procesar_reclamo, reclamos_sin_encolar
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def obtener_ejecutor() -> EjecutorBot:
    if get_settings().bot_modo == BotModo.SIMULADO:
        return EjecutorBotSimulado()
    # El ejecutor real (proceso aparte con bot-rpa) llega en el bloque 4.
    from app.services.bot_proceso import EjecutorBotProceso

    return EjecutorBotProceso.desde_settings(get_settings())


@celery_app.task(bind=True, name="reclamos.procesar", max_retries=None)
def procesar_reclamo_tarea(self: Task, reclamo_id: int) -> str:
    settings = get_settings()
    intento = self.request.retries + 1
    ultimo = self.request.retries >= settings.worker_reintentos
    with SessionLocal() as session:
        resultado = procesar_reclamo(
            session, reclamo_id, obtener_ejecutor(), intento=intento, ultimo_intento=ultimo
        )
    if resultado == Resultado.REINTENTAR:
        espera = settings.worker_espera_reintento_s * 2**self.request.retries
        raise self.retry(countdown=espera)
    return resultado.value


# Un reclamo recién creado se encola al instante; solo se "rescata" si lleva este tiempo esperando.
ESPERA_ANTES_DE_RESCATAR = timedelta(minutes=2)


@celery_app.task(name="reclamos.reencolar_sin_encolar")
def reencolar_sin_encolar(antiguedad_s: float = ESPERA_ANTES_DE_RESCATAR.total_seconds()) -> int:
    """Encola los reclamos que quedaron en "recibido" (Valkey caído al crearlos).

    Corre cada minuto con Celery Beat (`celery -A app.worker worker -B`) y al arrancar el worker.
    """
    with SessionLocal() as session:
        pendientes = reclamos_sin_encolar(session, timedelta(seconds=antiguedad_s))
    for reclamo_id in pendientes:
        procesar_reclamo_tarea.delay(reclamo_id)
    if pendientes:
        logger.info("Reencolados %d reclamos que no se habían encolado", len(pendientes))
    return len(pendientes)


@worker_ready.connect
def al_arrancar(**_: object) -> None:
    reencolar_sin_encolar.delay(0)
