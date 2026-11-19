from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field

from app.models import (
    ActorEvento,
    EstadoReclamo,
    Reclamo,
    ReclamoEvento,
    ReclamoItem,
    SolucionCompensacion,
    TipoReclamo,
)
from app.services.resolucion import describir_compensacion

RUTA_ARCHIVOS = "/api/v1/archivos"
RUTA_RECLAMOS = "/api/v1/reclamos"

# Estados en los que el cliente ve la compensación que le corresponde.
ESTADOS_CON_RESOLUCION = frozenset(
    {
        EstadoReclamo.VALIDADO,
        EstadoReclamo.EN_RESOLUCION,
        EstadoReclamo.RESUELTO,
        EstadoReclamo.CERRADO,
    }
)


class ReclamoItemEntrada(BaseModel):
    pedido_item_id: int
    cantidad_afectada: int = Field(ge=1)


class ReclamoItemOut(BaseModel):
    pedido_item_id: int
    producto: str
    cantidad_afectada: int

    @classmethod
    def desde(cls, item: ReclamoItem) -> Self:
        return cls(
            pedido_item_id=item.pedido_item_id,
            producto=item.pedido_item.producto.nombre,
            cantidad_afectada=item.cantidad_afectada,
        )


class ReclamoEventoOut(BaseModel):
    estado: EstadoReclamo
    mensaje: str
    actor: ActorEvento
    creado_en: datetime

    @classmethod
    def desde(cls, evento: ReclamoEvento) -> Self:
        return cls(
            estado=evento.estado,
            mensaje=evento.mensaje,
            actor=evento.actor,
            creado_en=evento.creado_en,
        )


class ReclamoResumen(BaseModel):
    codigo: str
    pedido_codigo: str
    tipo: TipoReclamo
    estado: EstadoReclamo
    creado_en: datetime
    actualizado_en: datetime

    @classmethod
    def desde(cls, reclamo: Reclamo) -> Self:
        return cls(
            codigo=reclamo.codigo,
            pedido_codigo=reclamo.pedido.codigo,
            tipo=reclamo.tipo,
            estado=reclamo.estado,
            creado_en=reclamo.creado_en,
            actualizado_en=reclamo.actualizado_en,
        )


class ResolucionOut(BaseModel):
    """Lo que el cliente recibe. Nunca incluye el motivo interno de escalamiento."""

    solucion: SolucionCompensacion
    monto: Decimal
    descripcion: str  # "un reembolso de S/ 8.90"
    numero_operacion: str | None
    # Video del bot registrando la compensación (ruta relativa a la API, con sesión).
    video_url: str | None

    @classmethod
    def desde(cls, reclamo: Reclamo) -> Self | None:
        if (
            reclamo.estado not in ESTADOS_CON_RESOLUCION
            or reclamo.solucion is None
            or reclamo.monto_compensacion is None
        ):
            return None
        con_video = any(e.exito and e.video for e in reclamo.ejecuciones_bot)
        return cls(
            solucion=reclamo.solucion,
            monto=reclamo.monto_compensacion,
            descripcion=describir_compensacion(reclamo.solucion, reclamo.monto_compensacion),
            numero_operacion=reclamo.numero_operacion,
            video_url=f"{RUTA_RECLAMOS}/{reclamo.codigo}/video" if con_video else None,
        )


class ReclamoDetalle(ReclamoResumen):
    descripcion: str
    # Ruta relativa a la API; la app le antepone EXPO_PUBLIC_API_URL y envía su sesión.
    foto_url: str | None
    items: list[ReclamoItemOut]
    eventos: list[ReclamoEventoOut]
    resolucion: ResolucionOut | None

    @classmethod
    def desde_reclamo(cls, reclamo: Reclamo) -> Self:
        return cls(
            **ReclamoResumen.desde(reclamo).model_dump(),
            descripcion=reclamo.descripcion,
            foto_url=f"{RUTA_ARCHIVOS}/{reclamo.foto_ruta}" if reclamo.foto_ruta else None,
            items=[ReclamoItemOut.desde(item) for item in reclamo.items],
            eventos=[ReclamoEventoOut.desde(evento) for evento in reclamo.eventos],
            resolucion=ResolucionOut.desde(reclamo),
        )
