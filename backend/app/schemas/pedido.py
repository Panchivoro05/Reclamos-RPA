"""Respuestas de pedidos. Los montos se envían como texto ("82.50") para no perder
precisión con los decimales de punto flotante."""

from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel

from app.models import CategoriaProducto, EstadoPedido, Pedido, PedidoItem, TipoReclamo


class PedidoItemOut(BaseModel):
    id: int
    producto: str
    categoria: CategoriaProducto
    cantidad: int
    precio_unitario: Decimal
    subtotal: Decimal
    # Unidades que todavía se pueden reclamar (las demás ya están en otro reclamo).
    cantidad_reclamable: int

    @classmethod
    def desde(cls, item: PedidoItem, reclamadas: int = 0) -> Self:
        return cls(
            id=item.id,
            producto=item.producto.nombre,
            categoria=item.producto.categoria,
            cantidad=item.cantidad,
            precio_unitario=item.precio_unitario,
            subtotal=item.precio_unitario * item.cantidad,
            cantidad_reclamable=max(item.cantidad - reclamadas, 0),
        )


class PedidoResumen(BaseModel):
    codigo: str
    estado: EstadoPedido
    total: Decimal
    local: str
    cantidad_productos: int
    creado_en: datetime
    entregado_en: datetime | None

    @classmethod
    def desde(cls, pedido: Pedido) -> Self:
        return cls(
            codigo=pedido.codigo,
            estado=pedido.estado,
            total=pedido.total,
            local=pedido.local,
            cantidad_productos=sum(item.cantidad for item in pedido.items),
            creado_en=pedido.creado_en,
            entregado_en=pedido.entregado_en,
        )


class PedidoDetalle(PedidoResumen):
    direccion_entrega: str
    items: list[PedidoItemOut]
    # Vacía si el pedido ya no admite reclamos (la app oculta el botón).
    tipos_reclamo_disponibles: list[TipoReclamo]
    # Tipos para los que la foto es obligatoria (según las reglas configuradas).
    tipos_con_foto_obligatoria: list[TipoReclamo]

    @classmethod
    def desde_pedido(
        cls,
        pedido: Pedido,
        tipos_disponibles: list[TipoReclamo],
        tipos_con_foto: list[TipoReclamo],
        unidades_reclamadas: dict[int, int],
    ) -> Self:
        return cls(
            **PedidoResumen.desde(pedido).model_dump(),
            direccion_entrega=pedido.direccion_entrega,
            items=[
                PedidoItemOut.desde(item, unidades_reclamadas.get(item.id, 0))
                for item in pedido.items
            ],
            tipos_reclamo_disponibles=tipos_disponibles,
            tipos_con_foto_obligatoria=tipos_con_foto,
        )
