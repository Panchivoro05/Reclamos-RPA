"""Tareas de la cola "notificaciones" (worker aparte: `-Q notificaciones`).

Van separadas de la cola del bot porque el worker del bot procesa un reclamo a la vez y cada
ejecución tarda decenas de segundos: un aviso no debe esperar detrás de eso.
"""

from celery import Task

from app.core.db import SessionLocal
from app.services.notificaciones import notificar_push
from app.services.push import ErrorEnvio, get_notificador_push
from app.worker.celery_app import celery_app

REINTENTOS = 3


@celery_app.task(bind=True, name="notificaciones.enviar", max_retries=REINTENTOS)
def enviar_notificaciones(self: Task, evento_id: int) -> str:
    try:
        with SessionLocal() as session:
            return notificar_push(session, evento_id, get_notificador_push()).value
    except ErrorEnvio as error:
        # Expo no respondió: 10 s, 20 s, 40 s. Después se da por perdida (el cliente igual
        # ve el cambio en la app).
        raise self.retry(exc=error, countdown=10 * 2**self.request.retries) from error
