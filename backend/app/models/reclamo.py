from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Sequence,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, creado_en_column, pg_enum
from app.models.enums import ActorEvento, EstadoReclamo, SolucionCompensacion, TipoReclamo
from app.models.pedido import Pedido, PedidoItem

# Correlativo del código visible RC-AAAA-NNNNNN. Una secuencia de PostgreSQL
# evita que dos reclamos simultáneos reciban el mismo número.
reclamo_codigo_seq = Sequence("reclamo_codigo_seq", metadata=Base.metadata)


class Reclamo(Base):
    __tablename__ = "reclamos"
    __table_args__ = (
        # Un solo reclamo abierto por pedido y tipo. El servicio lo valida antes, pero
        # este índice lo garantiza aunque lleguen dos peticiones al mismo tiempo.
        Index(
            "uq_reclamos_abierto_pedido_tipo",
            "pedido_id",
            "tipo",
            unique=True,
            postgresql_where=text("estado NOT IN ('resuelto', 'cerrado')"),
        ),
    )

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
    # Hash perceptual de la foto (16 hex): detecta la misma foto en otro reclamo.
    foto_hash: Mapped[str | None] = mapped_column(String(16))
    creado_en: Mapped[datetime] = creado_en_column()
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Resolución (la completa el worker de la fase 3).
    solucion: Mapped[SolucionCompensacion | None] = mapped_column(
        pg_enum(SolucionCompensacion, "solucion_compensacion")
    )
    monto_compensacion: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    numero_operacion: Mapped[str | None] = mapped_column(String(20))
    # Motivo interno del escalamiento (lo ve el agente, no el cliente).
    motivo_escalamiento: Mapped[str | None] = mapped_column(Text)

    pedido: Mapped[Pedido] = relationship()
    items: Mapped[list["ReclamoItem"]] = relationship(
        back_populates="reclamo", cascade="all, delete-orphan", order_by="ReclamoItem.id"
    )
    eventos: Mapped[list["ReclamoEvento"]] = relationship(
        back_populates="reclamo",
        cascade="all, delete-orphan",
        order_by="(ReclamoEvento.creado_en, ReclamoEvento.id)",
    )
    ejecuciones_bot: Mapped[list["EjecucionBot"]] = relationship(
        back_populates="reclamo", cascade="all, delete-orphan", order_by="EjecucionBot.id"
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


class EjecucionBot(Base):
    """Cada intento del bot RPA sobre un reclamo, con su resultado y su evidencia."""

    __tablename__ = "ejecuciones_bot"

    id: Mapped[int] = mapped_column(primary_key=True)
    reclamo_id: Mapped[int] = mapped_column(
        ForeignKey("reclamos.id", ondelete="CASCADE"), index=True
    )
    intento: Mapped[int]
    exito: Mapped[bool]
    codigo_error: Mapped[str | None] = mapped_column(String(40))
    mensaje: Mapped[str] = mapped_column(Text)
    numero_operacion: Mapped[str | None] = mapped_column(String(20))
    duracion_s: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    # Carpeta de evidencia dentro del almacenamiento (capturas, video y resultado.json).
    evidencia: Mapped[str | None] = mapped_column(String(255))
    video: Mapped[str | None] = mapped_column(String(255))
    pasos: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    creado_en: Mapped[datetime] = creado_en_column()

    reclamo: Mapped[Reclamo] = relationship(back_populates="ejecuciones_bot")
