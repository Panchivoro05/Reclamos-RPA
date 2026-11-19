"""Avisos al cliente por cada cambio de estado de su reclamo (push; en el bloque 6, correo).

Lo ejecuta la tarea `notificaciones.enviar` del worker de notificaciones, en una cola aparte de
la del bot: así un aviso no espera a que el bot termine con otro reclamo.

Una sola vez por evento y canal: antes de enviar se "reserva" una fila en `notificaciones`
(restricción única evento_id + canal). Si la tarea se repite (reintento, mensaje duplicado de
la cola), encuentra la reserva y no vuelve a enviar. Si el envío falla por algo técnico, la
reserva se borra para que el reintento pueda enviarlo.
"""

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models import (
    CanalNotificacion,
    EstadoNotificacion,
    EstadoReclamo,
    Notificacion,
    ReclamoEvento,
)
from app.services import dispositivos
from app.services.push import ErrorEnvio, MensajePush, NotificadorPush

logger = logging.getLogger(__name__)

TITULOS: dict[EstadoReclamo, str] = {
    EstadoReclamo.RECIBIDO: "Recibimos tu reclamo",
    EstadoReclamo.EN_VALIDACION: "Estamos revisando tu reclamo",
    EstadoReclamo.VALIDADO: "¡Tu reclamo fue aprobado!",
    EstadoReclamo.EN_RESOLUCION: "Registrando tu compensación",
    EstadoReclamo.RESUELTO: "¡Reclamo resuelto!",
    EstadoReclamo.ESCALADO: "Tu reclamo está en revisión",
    EstadoReclamo.CERRADO: "Reclamo cerrado",
}


def enlace_reclamo(codigo: str) -> str:
    """Enlace profundo de la app: al tocar la notificación se abre el detalle."""
    return f"burgerya://reclamos/{codigo}"


def notificar_push(session: Session, evento_id: int, push: NotificadorPush) -> EstadoNotificacion:
    evento = session.scalars(
        select(ReclamoEvento)
        .where(ReclamoEvento.id == evento_id)
        .options(joinedload(ReclamoEvento.reclamo))
    ).one_or_none()
    if evento is None:
        return EstadoNotificacion.OMITIDA

    registro = _reservar(session, evento_id, CanalNotificacion.PUSH)
    if registro is None:
        logger.info("Push del evento %s ya enviado o en curso: no se repite", evento_id)
        return EstadoNotificacion.OMITIDA

    destinos = dispositivos.activos(session, evento.reclamo.cliente_id)
    if not destinos:
        return _terminar(session, registro, EstadoNotificacion.OMITIDA, 0, "Sin dispositivos")

    reclamo = evento.reclamo
    mensajes = [
        MensajePush(
            token=d.token,
            titulo=f"{TITULOS[evento.estado]} · {reclamo.codigo}",
            cuerpo=evento.mensaje,
            datos={
                "codigo": reclamo.codigo,
                "estado": evento.estado.value,
                "url": enlace_reclamo(reclamo.codigo),
            },
        )
        for d in destinos
    ]
    try:
        resultados = push.enviar(mensajes)
    except ErrorEnvio:
        # Se libera la reserva para que el reintento de la tarea pueda enviarlo.
        session.delete(registro)
        session.commit()
        raise

    dispositivos.desactivar_tokens(session, [r.token for r in resultados if r.token_invalido])
    enviados = sum(r.ok for r in resultados)
    errores = "; ".join(f"{r.error}: {r.mensaje}".strip(": ") for r in resultados if not r.ok)
    estado = EstadoNotificacion.ENVIADA if enviados else EstadoNotificacion.FALLIDA
    return _terminar(session, registro, estado, enviados, errores or None)


def _reservar(session: Session, evento_id: int, canal: CanalNotificacion) -> Notificacion | None:
    registro = Notificacion(evento_id=evento_id, canal=canal, estado=EstadoNotificacion.ENVIANDO)
    session.add(registro)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return None
    return registro


def _terminar(
    session: Session,
    registro: Notificacion,
    estado: EstadoNotificacion,
    destinatarios: int,
    detalle: str | None,
) -> EstadoNotificacion:
    registro.estado = estado
    registro.destinatarios = destinatarios
    registro.detalle = detalle
    session.commit()
    logger.info("Push del evento %s: %s (%d)", registro.evento_id, estado.value, destinatarios)
    return estado
