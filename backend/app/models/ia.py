"""Registro de cada llamada a la IA: qué se pidió, cuánto tardó, cuánto costó y qué respondió."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, creado_en_column, pg_enum
from app.models.enums import OperacionIA


class LlamadaIA(Base):
    """Una llamada al proveedor de IA (exitosa o no): sirve para auditar y medir costo y demora."""

    __tablename__ = "llamadas_ia"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nulo en las llamadas que no son de un reclamo (el asistente de consultas).
    reclamo_id: Mapped[int | None] = mapped_column(
        ForeignKey("reclamos.id", ondelete="CASCADE"), index=True
    )
    operacion: Mapped[OperacionIA] = mapped_column(pg_enum(OperacionIA, "operacion_ia"))
    proveedor: Mapped[str] = mapped_column(String(20))
    modelo: Mapped[str] = mapped_column(String(60))
    exito: Mapped[bool]
    error: Mapped[str | None] = mapped_column(Text)
    tokens_entrada: Mapped[int] = mapped_column(default=0)
    tokens_salida: Mapped[int] = mapped_column(default=0)
    latencia_ms: Mapped[int]
    # Aproximado: tokens por el precio por millón configurado (IA_PRECIO_*).
    costo_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    # Lo que respondió la IA (ya validado), para que el agente vea por qué se escaló.
    resultado: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    creado_en: Mapped[datetime] = creado_en_column()
