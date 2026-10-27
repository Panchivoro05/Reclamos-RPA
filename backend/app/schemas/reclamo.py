from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field

from app.models import (
    ActorEvento,
    EstadoReclamo,
    Reclamo,
    ReclamoEvento,
    ReclamoItem,
    TipoReclamo,
)

RUTA_ARCHIVOS = "/api/v1/archivos"


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


class ReclamoDetalle(ReclamoResumen):
    descripcion: str
    # Ruta relativa a la API; la app le antepone EXPO_PUBLIC_API_URL y envía su sesión.
    foto_url: str | None
    items: list[ReclamoItemOut]
    eventos: list[ReclamoEventoOut]

    @classmethod
    def desde_reclamo(cls, reclamo: Reclamo) -> Self:
        return cls(
            **ReclamoResumen.desde(reclamo).model_dump(),
            descripcion=reclamo.descripcion,
            foto_url=f"{RUTA_ARCHIVOS}/{reclamo.foto_ruta}" if reclamo.foto_ruta else None,
            items=[ReclamoItemOut.desde(item) for item in reclamo.items],
            eventos=[ReclamoEventoOut.desde(evento) for evento in reclamo.eventos],
        )
