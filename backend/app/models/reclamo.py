from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Sequence, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, creado_en_column, pg_enum
from app.models.enums import ActorEvento, EstadoReclamo, TipoReclamo
from app.models.pedido import Pedido, PedidoItem

# Correlativo del código visible RC-AAAA-NNNNNN. Una secuencia de PostgreSQL
# evita que dos reclamos simultáneos reciban el mismo número.
reclamo_codigo_seq = Sequence("reclamo_codigo_seq", metadata=Base.metadata)


class Reclamo(Base):
    __tablename__ = "reclamos"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    tipo: Mapped[TipoReclamo] = mapped_column(pg_enum(TipoReclamo, "tipo_reclamo"))
    estado: Mapped[EstadoReclamo] = mapped_column(
        pg_enum(EstadoReclamo, "estado_reclamo"), default=EstadoReclamo.RECIBIDO
    )
    descripcion: Mapped[str] = mapped_column(Text)
    foto_ruta: Mapped[str | None] = mapped_column(String(255))
    creado_en: Mapped[datetime] = creado_en_column()
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    pedido: Mapped[Pedido] = relationship()
    items: Mapped[list["ReclamoItem"]] = relationship(
        back_populates="reclamo", cascade="all, delete-orphan", order_by="ReclamoItem.id"
    )
    eventos: Mapped[list["ReclamoEvento"]] = relationship(
        back_populates="reclamo",
        cascade="all, delete-orphan",
        order_by="(ReclamoEvento.creado_en, ReclamoEvento.id)",
    )


class ReclamoItem(Base):
    __tablename__ = "reclamo_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    reclamo_id: Mapped[int] = mapped_column(
        ForeignKey("reclamos.id", ondelete="CASCADE"), index=True
    )
    pedido_item_id: Mapped[int] = mapped_column(ForeignKey("pedido_items.id"))
    cantidad_afectada: Mapped[int]

    reclamo: Mapped[Reclamo] = relationship(back_populates="items")
    pedido_item: Mapped[PedidoItem] = relationship(lazy="joined")


class ReclamoEvento(Base):
    __tablename__ = "reclamo_eventos"

    id: Mapped[int] = mapped_column(primary_key=True)
    reclamo_id: Mapped[int] = mapped_column(
        ForeignKey("reclamos.id", ondelete="CASCADE"), index=True
    )
    estado: Mapped[EstadoReclamo] = mapped_column(pg_enum(EstadoReclamo, "estado_reclamo"))
    mensaje: Mapped[str] = mapped_column(Text)
    actor: Mapped[ActorEvento] = mapped_column(pg_enum(ActorEvento, "actor_evento"))
    creado_en: Mapped[datetime] = creado_en_column()

    reclamo: Mapped[Reclamo] = relationship(back_populates="eventos")
