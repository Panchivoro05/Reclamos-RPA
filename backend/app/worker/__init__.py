"""Worker de Celery (broker: Valkey).

Arranque:  celery -A app.worker worker --loglevel info
Una sola tarea a la vez (concurrency 1): SISCAJA es "una terminal de caja" y el bot la usa
como lo haría un cajero, un reclamo detrás de otro.
"""

from app.worker.celery_app import celery_app
from app.worker.tareas import procesar_reclamo_tarea

__all__ = ["celery_app", "procesar_reclamo_tarea"]
