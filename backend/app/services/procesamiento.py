"""Procesamiento automático de un reclamo: reglas, antifraude y bot RPA.

recibido → en_validacion → validado → en_resolucion → resuelto
                 └──────────→ escalado ←──────────┘

Cada cambio de estado deja un evento (la línea de tiempo del cliente). Se puede volver a
ejecutar sin riesgo: retoma desde el estado en que quedó el reclamo y no repite lo hecho.
La tarea de Celery (app.worker) solo llama a `procesar_reclamo` y decide si reintenta.
"""

import logging
from datetime import timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.tiempo import ahora_utc
from app.models import (
    ActorEvento,
    EjecucionBot,
    EstadoReclamo,
    Pedido,
    PedidoItem,
    Reclamo,
    ReclamoEvento,
    ReclamoItem,
    TipoReclamo,
)
from app.services.bot import EjecutorBot, ResultadoBot, SolicitudBot
from app.services.resolucion import decidir, describir_compensacion

logger = logging.getLogger(__name__)

MENSAJE_EN_VALIDACION = "Estamos revisando tu reclamo."
MENSAJE_ESCALADO = (
    "Tu caso necesita una revisión adicional. Un agente de BurgerYa lo atenderá pronto."
)
MENSAJE_EN_RESOLUCION = "Estamos registrando tu compensación en nuestro sistema de caja."

TIPOS_LEGIBLES = {
    TipoReclamo.PRODUCTO_EQUIVOCADO: "Producto equivocado",
    TipoReclamo.PEDIDO_INCOMPLETO: "Pedido incompleto",
    TipoReclamo.MAL_ESTADO: "Producto en mal estado",
    TipoReclamo.DEMORA: "Demora en la entrega",
}

# Estados desde los que el worker todavía tiene trabajo pendiente.
ESTADOS_PENDIENTES = frozenset(
    {
        EstadoReclamo.RECIBIDO,
        EstadoReclamo.EN_VALIDACION,
        EstadoReclamo.VALIDADO,
        EstadoReclamo.EN_RESOLUCION,
    }
)


class Resultado(StrEnum):
    RESUELTO = "resuelto"
    ESCALADO = "escalado"
    REINTENTAR = "reintentar"  # error técnico del bot: la tarea vuelve a intentar más tarde
    SIN_CAMBIOS = "sin_cambios"  # ya estaba terminado (mensaje duplicado de la cola)


def procesar_reclamo(
    session: Session,
    reclamo_id: int,
    ejecutor: EjecutorBot,
    *,
    intento: int = 1,
    ultimo_intento: bool = True,
) -> Resultado:
    reclamo = _bloquear(session, reclamo_id)
    if reclamo is None or reclamo.estado not in ESTADOS_PENDIENTES:
        session.rollback()
        return Resultado.SIN_CAMBIOS

    # 1. Reglas y antifraude (si se cortó a mitad de la validación, se valida de nuevo).
    if reclamo.estado in (EstadoReclamo.RECIBIDO, EstadoReclamo.EN_VALIDACION):
        if reclamo.estado == EstadoReclamo.RECIBIDO:
            _cambiar_estado(session, reclamo, EstadoReclamo.EN_VALIDACION, MENSAJE_EN_VALIDACION)
        decision = decidir(session, reclamo)
        if not decision.aprobada or decision.solucion is None:
            return _escalar(session, reclamo, str(decision.motivo_escalamiento))
        reclamo.solucion = decision.solucion
        reclamo.monto_compensacion = decision.monto
        _cambiar_estado(
            session,
            reclamo,
            EstadoReclamo.VALIDADO,
            f"¡Tu reclamo fue aprobado! Te corresponde "
            f"{describir_compensacion(decision.solucion, decision.monto)}.",
        )
        reclamo = _bloquear(session, reclamo_id)
        assert reclamo is not None

    # 2. El bot registra la compensación en SISCAJA.
    if reclamo.estado == EstadoReclamo.VALIDADO:
        _cambiar_estado(
            session,
            reclamo,
            EstadoReclamo.EN_RESOLUCION,
            MENSAJE_EN_RESOLUCION,
            actor=ActorEvento.BOT,
        )
        reclamo = _bloquear(session, reclamo_id)
        assert reclamo is not None

    solicitud = _solicitud_para_el_bot(reclamo)
    # El bot tarda segundos: no se mantiene la fila bloqueada mientras trabaja.
    session.commit()
    logger.info("Reclamo %s: lanzando el bot (intento %d)", reclamo.codigo, intento)
    resultado = ejecutor.resolver(solicitud)

    reclamo = _bloquear(session, reclamo_id)
    assert reclamo is not None
    if reclamo.estado != EstadoReclamo.EN_RESOLUCION:
        # Otro proceso lo terminó mientras el bot trabajaba.
        session.rollback()
        return Resultado.SIN_CAMBIOS
    _registrar_ejecucion(session, reclamo, resultado, intento)

    if resultado.exito:
        assert reclamo.solucion is not None and reclamo.monto_compensacion is not None
        reclamo.numero_operacion = resultado.numero_operacion
        descripcion = describir_compensacion(reclamo.solucion, reclamo.monto_compensacion)
        _cambiar_estado(
            session,
            reclamo,
            EstadoReclamo.RESUELTO,
            f"¡Listo! Registramos {descripcion}. "
            f"Número de operación: {resultado.numero_operacion}.",
            actor=ActorEvento.BOT,
        )
        return Resultado.RESUELTO

    if resultado.es_error_tecnico and not ultimo_intento:
        session.commit()  # guarda el intento fallido; el cliente no ve nada todavía
        logger.warning(
            "Reclamo %s: el bot falló (%s); se reintentará", reclamo.codigo, resultado.codigo_error
        )
        return Resultado.REINTENTAR

    return _escalar(
        session,
        reclamo,
        f"El bot no pudo registrar la compensación ({resultado.codigo_error}): {resultado.mensaje}",
    )


def reclamos_sin_encolar(session: Session, antiguedad: timedelta) -> list[int]:
    """Reclamos que siguen en "recibido" después de `antiguedad` (Valkey estaba caído al crearlos).

    Solo se miran los "recibido": si el worker murió a mitad de un reclamo, Celery vuelve a
    entregar ese mensaje (acks_late) y los reintentos programados ya están en Valkey.
    """
    consulta = (
        select(Reclamo.id)
        .where(
            Reclamo.estado == EstadoReclamo.RECIBIDO,
            Reclamo.creado_en <= ahora_utc() - antiguedad,
        )
        .order_by(Reclamo.creado_en)
    )
    return list(session.scalars(consulta))


# ---------- Ayudas ----------


def _bloquear(session: Session, reclamo_id: int) -> Reclamo | None:
    """Lee el reclamo bloqueando su fila: dos workers no pueden avanzarlo a la vez."""
    consulta = (
        select(Reclamo)
        .where(Reclamo.id == reclamo_id)
        .options(
            selectinload(Reclamo.pedido).selectinload(Pedido.items).joinedload(PedidoItem.producto),
            selectinload(Reclamo.items)
            .joinedload(ReclamoItem.pedido_item)
            .joinedload(PedidoItem.producto),
        )
        .with_for_update(of=Reclamo)
        .execution_options(populate_existing=True)
    )
    return session.scalars(consulta).one_or_none()


def _cambiar_estado(
    session: Session,
    reclamo: Reclamo,
    estado: EstadoReclamo,
    mensaje: str,
    actor: ActorEvento = ActorEvento.SISTEMA,
) -> None:
    reclamo.estado = estado
    session.add(ReclamoEvento(reclamo_id=reclamo.id, estado=estado, mensaje=mensaje, actor=actor))
    session.commit()
    logger.info("Reclamo %s → %s", reclamo.codigo, estado.value)


def _escalar(session: Session, reclamo: Reclamo, motivo: str) -> Resultado:
    reclamo.motivo_escalamiento = motivo
    _cambiar_estado(session, reclamo, EstadoReclamo.ESCALADO, MENSAJE_ESCALADO)
    logger.warning("Reclamo %s escalado: %s", reclamo.codigo, motivo)
    return Resultado.ESCALADO


def _solicitud_para_el_bot(reclamo: Reclamo) -> SolicitudBot:
    assert reclamo.solucion is not None and reclamo.monto_compensacion is not None
    # El código del reclamo va en el motivo: SISCAJA lo guarda y sirve para no repetir la
    # compensación si el bot se reintenta (ver bot-rpa).
    motivo = f"{reclamo.codigo} - {TIPOS_LEGIBLES[reclamo.tipo]}: {reclamo.descripcion}"
    return SolicitudBot(
        reclamo_codigo=reclamo.codigo,
        pedido_codigo=reclamo.pedido.codigo,
        solucion=reclamo.solucion,
        monto=reclamo.monto_compensacion,
        motivo=motivo[:480],
        items_esperados=[
            {"producto": item.pedido_item.producto.nombre, "cantidad": item.cantidad_afectada}
            for item in reclamo.items
        ],
        total_esperado=reclamo.pedido.total,
    )


def _registrar_ejecucion(
    session: Session, reclamo: Reclamo, resultado: ResultadoBot, intento: int
) -> None:
    session.add(
        EjecucionBot(
            reclamo_id=reclamo.id,
            intento=intento,
            exito=resultado.exito,
            codigo_error=resultado.codigo_error,
            mensaje=resultado.mensaje,
            numero_operacion=resultado.numero_operacion,
            duracion_s=resultado.duracion_s,
            pasos=resultado.pasos,
        )
    )
