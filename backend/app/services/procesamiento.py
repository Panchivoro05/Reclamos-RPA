"""Procesamiento automático de un reclamo: reglas, antifraude, IA y bot RPA.

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

from app.core.moneda import formato_soles
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
from app.services.almacenamiento import AlmacenamientoArchivos, get_almacenamiento
from app.services.analisis import (
    AnalisisIA,
    analizar_con_ia,
    control_foto_repetida,
    controles_ia,
    hash_foto,
    preparar_entradas,
    reclamo_con_la_misma_foto,
)
from app.services.bot import EjecutorBot, ResultadoBot, SolicitudBot
from app.services.eventos import CambioEstado, publicar_cambio
from app.services.evidencia import guardar_evidencia
from app.services.ia import ErrorIA, ProveedorIA
from app.services.mensajes import redactar
from app.services.reglas import obtener_politica
from app.services.resolucion import (
    SOLUCIONES_CON_DINERO,
    Decision,
    decidir,
    describir_compensacion,
)

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
    REINTENTAR = "reintentar"  # error técnico (bot o IA): la tarea vuelve a intentar más tarde
    SIN_CAMBIOS = "sin_cambios"  # ya estaba terminado (mensaje duplicado de la cola)


def procesar_reclamo(
    session: Session,
    reclamo_id: int,
    ejecutor: EjecutorBot,
    *,
    intento: int = 1,
    ultimo_intento: bool = True,
    almacenamiento: AlmacenamientoArchivos | None = None,
    ia: ProveedorIA | None = None,
) -> Resultado:
    """Avanza el reclamo todo lo posible.

    Con `almacenamiento`, guarda la evidencia del bot. Con `ia`, analiza el texto y la foto
    (el worker siempre la pasa; sin ella, solo se aplican las reglas).
    """
    reclamo = _bloquear(session, reclamo_id)
    if reclamo is None or reclamo.estado not in ESTADOS_PENDIENTES:
        session.rollback()
        return Resultado.SIN_CAMBIOS

    # 1. Reglas, antifraude e IA (si se cortó a mitad de la validación, se valida de nuevo).
    if reclamo.estado in (EstadoReclamo.RECIBIDO, EstadoReclamo.EN_VALIDACION):
        if reclamo.estado == EstadoReclamo.RECIBIDO:
            _cambiar_estado(session, reclamo, EstadoReclamo.EN_VALIDACION, MENSAJE_EN_VALIDACION)
        foto = _leer_foto(reclamo, almacenamiento)
        analisis: AnalisisIA | None = None
        if ia is not None:
            entradas = preparar_entradas(reclamo, foto)
            # La IA puede tardar decenas de segundos: no se mantiene la fila bloqueada.
            session.commit()
            try:
                analisis = analizar_con_ia(session, reclamo_id, entradas, ia)
                session.commit()  # guarda el registro de las llamadas
            except ErrorIA as error:
                session.commit()  # guarda el registro de la llamada fallida
                if not ultimo_intento:
                    logger.warning(
                        "Reclamo %d: la IA falló (%s); se reintentará", reclamo_id, error
                    )
                    return Resultado.REINTENTAR
                reclamo = _bloquear(session, reclamo_id)
                if reclamo is None or reclamo.estado != EstadoReclamo.EN_VALIDACION:
                    session.rollback()
                    return Resultado.SIN_CAMBIOS
                return _escalar(
                    session, reclamo, f"No se pudo completar el análisis con IA: {error}", ia
                )
            reclamo = _bloquear(session, reclamo_id)
            if reclamo is None or reclamo.estado != EstadoReclamo.EN_VALIDACION:
                # Otro proceso lo avanzó mientras la IA trabajaba.
                session.rollback()
                return Resultado.SIN_CAMBIOS
        decision = _decidir_con_analisis(session, reclamo, foto, analisis)
        if not decision.aprobada or decision.solucion is None:
            return _escalar(session, reclamo, str(decision.motivo_escalamiento), ia)
        reclamo.solucion = decision.solucion
        reclamo.monto_compensacion = decision.monto
        plantilla = (
            f"¡Tu reclamo fue aprobado! Te corresponde "
            f"{describir_compensacion(decision.solucion, decision.monto)}."
        )
        _cambiar_estado(
            session,
            reclamo,
            EstadoReclamo.VALIDADO,
            redactar(
                session,
                reclamo,
                EstadoReclamo.VALIDADO,
                plantilla,
                _datos_obligatorios(reclamo),
                ia,
            ),
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
    _registrar_ejecucion(session, reclamo, resultado, intento, almacenamiento)

    if resultado.exito:
        assert reclamo.solucion is not None and reclamo.monto_compensacion is not None
        reclamo.numero_operacion = resultado.numero_operacion
        descripcion = describir_compensacion(reclamo.solucion, reclamo.monto_compensacion)
        plantilla = (
            f"¡Listo! Registramos {descripcion}. Número de operación: {resultado.numero_operacion}."
        )
        _cambiar_estado(
            session,
            reclamo,
            EstadoReclamo.RESUELTO,
            redactar(
                session,
                reclamo,
                EstadoReclamo.RESUELTO,
                plantilla,
                [*_datos_obligatorios(reclamo), str(resultado.numero_operacion)],
                ia,
            ),
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
        ia,
    )


def _leer_foto(reclamo: Reclamo, almacenamiento: AlmacenamientoArchivos | None) -> bytes | None:
    if not reclamo.foto_ruta:
        return None
    return (almacenamiento or get_almacenamiento()).leer(reclamo.foto_ruta)


def _decidir_con_analisis(
    session: Session, reclamo: Reclamo, foto: bytes | None, analisis: AnalisisIA | None
) -> Decision:
    """Reglas y antifraude, más la foto repetida y (si hubo) los controles de la IA."""
    decision = decidir(session, reclamo)
    extra = []
    if foto:
        reclamo.foto_hash = reclamo.foto_hash or hash_foto(foto)
        if reclamo.foto_hash:
            extra.append(control_foto_repetida(reclamo_con_la_misma_foto(session, reclamo)))
    if analisis is not None:
        umbral = obtener_politica(session).umbral_confianza_ia
        extra += controles_ia(reclamo.tipo, analisis, umbral)
    return decision.con_controles(extra)


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
    evento = ReclamoEvento(reclamo_id=reclamo.id, estado=estado, mensaje=mensaje, actor=actor)
    session.add(evento)
    session.commit()
    logger.info("Reclamo %s → %s", reclamo.codigo, estado.value)
    # Después del commit: la app solo se entera de lo que ya está guardado.
    publicar_cambio(CambioEstado.desde_evento(reclamo, evento))


def _datos_obligatorios(reclamo: Reclamo) -> list[str]:
    """Lo que el mensaje redactado por la IA debe repetir tal cual (el monto, si lo hay)."""
    if reclamo.solucion in SOLUCIONES_CON_DINERO and reclamo.monto_compensacion is not None:
        return [formato_soles(reclamo.monto_compensacion)]
    return []


def _escalar(
    session: Session, reclamo: Reclamo, motivo: str, ia: ProveedorIA | None = None
) -> Resultado:
    reclamo.motivo_escalamiento = motivo
    # La IA no recibe el motivo: es interno (para el agente), el cliente no debe verlo.
    mensaje = redactar(session, reclamo, EstadoReclamo.ESCALADO, MENSAJE_ESCALADO, [], ia)
    _cambiar_estado(session, reclamo, EstadoReclamo.ESCALADO, mensaje)
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
    session: Session,
    reclamo: Reclamo,
    resultado: ResultadoBot,
    intento: int,
    almacenamiento: AlmacenamientoArchivos | None,
) -> None:
    evidencia = None
    if almacenamiento is not None:
        try:
            evidencia = guardar_evidencia(almacenamiento, resultado, reclamo.codigo, intento)
        except OSError:
            # Sin evidencia el reclamo igual se resuelve: el resultado ya está en SISCAJA.
            logger.exception("No se pudo guardar la evidencia del reclamo %s", reclamo.codigo)
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
            evidencia=evidencia.carpeta if evidencia else None,
            video=evidencia.video if evidencia else None,
        )
    )
