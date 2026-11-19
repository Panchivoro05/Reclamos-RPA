"""Dispositivos del cliente (tokens de Expo Push) y registro de notificaciones enviadas."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, creado_en_column, pg_enum
from app.models.enums import CanalNotificacion, EstadoNotificacion, PlataformaDispositivo


class Dispositivo(Base):
    """Un celular donde el cliente inició sesión. El token lo entrega Expo (expo-notifications)."""

    __tablename__ = "dispositivos"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("clientes.id", ondelete="CASCADE"), index=True
    )
    # Un token es de un solo celular: si otro cliente inicia sesión en él, pasa a ese cliente.
    token: Mapped[str] = mapped_column(String(255), unique=True)
    plataforma: Mapped[PlataformaDispositivo] = mapped_column(
        pg_enum(PlataformaDispositivo, "plataforma_dispositivo")
    )
    # Se desactiva al cerrar sesión o cuando Expo avisa que la app se desinstaló.
    activo: Mapped[bool] = mapped_column(default=True)
    creado_en: Mapped[datetime] = creado_en_column()
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Notificacion(Base):
    """Una notificación por evento y canal: la restricción única impide enviarla dos veces."""

    __tablename__ = "notificaciones"
    __table_args__ = (UniqueConstraint("evento_id", "canal"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Sin índice propio: la restricción única (evento_id, canal) ya sirve para buscar por evento.
    evento_id: Mapped[int] = mapped_column(ForeignKey("reclamo_eventos.id", ondelete="CASCADE"))
    canal: Mapped[CanalNotificacion] = mapped_column(
        pg_enum(CanalNotificacion, "canal_notificacion")
    )
    estado: Mapped[EstadoNotificacion] = mapped_column(
        pg_enum(EstadoNotificacion, "estado_notificacion")
    )
    destinatarios: Mapped[int] = mapped_column(default=0)
    detalle: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = creado_en_column()
