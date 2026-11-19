from celery import Celery

from app.core.config import get_settings

celery_app = Celery("reclamos", broker=get_settings().valkey_url, include=["app.worker.tareas"])
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # No se guardan resultados: el estado vive en PostgreSQL (reclamos y eventos).
    task_ignore_result=True,
    # El mensaje se confirma al TERMINAR la tarea: si el worker muere a mitad, otro la retoma.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_concurrency=1,
    # Si Valkey no responde, la API no se queda colgada esperando para encolar.
    broker_connection_timeout=3,
    broker_connection_retry_on_startup=True,
    # Celery Beat: rescata cada minuto los reclamos que no se pudieron encolar.
    beat_schedule={
        "reencolar-sin-encolar": {"task": "reclamos.reencolar_sin_encolar", "schedule": 60.0},
    },
    beat_schedule_filename="/tmp/reclamos-celerybeat-schedule",
)
