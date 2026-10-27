from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, creado_en_column, pg_enum
from app.models.cliente import Cliente
from app.models.enums import EstadoPedido
from app.models.producto import Producto


class Pedido(Base):
    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    estado: Mapped[EstadoPedido] = mapped_column(pg_enum(EstadoPedido, "estado_pedido"))
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    direccion_entrega: Mapped[str] = mapped_column(String(255))
    local: Mapped[str] = mapped_column(String(120))
    creado_en: Mapped[datetime] = creado_en_column()
    entregado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    cliente: Mapped[Cliente] = relationship()
    items: Mapped[list["PedidoItem"]] = relationship(
        back_populates="pedido", cascade="all, delete-orphan", order_by="PedidoItem.id"
    )


class PedidoItem(Base):
    __tablename__ = "pedido_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id", ondelete="CASCADE"), index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"))
    cantidad: Mapped[int]
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    pedido: Mapped[Pedido] = relationship(back_populates="items")
    producto: Mapped[Producto] = relationship(lazy="joined")
