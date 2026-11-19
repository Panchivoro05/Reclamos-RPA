"""Reglas de resolución y política antifraude: configurables en la base, no en el código.

En la fase 6 el panel web las editará; mientras tanto se cambian con SQL.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pg_enum
from app.models.enums import BaseMonto, SolucionCompensacion, TipoReclamo


class ReglaResolucion(Base):
    """Qué solución corresponde a cada tipo de reclamo y cómo se calcula el monto."""

    __tablename__ = "reglas_resolucion"

    tipo: Mapped[TipoReclamo] = mapped_column(
        pg_enum(TipoReclamo, "tipo_reclamo"), primary_key=True
    )
    solucion: Mapped[SolucionCompensacion] = mapped_column(
        pg_enum(SolucionCompensacion, "solucion_compensacion")
    )
    base_monto: Mapped[BaseMonto] = mapped_column(pg_enum(BaseMonto, "base_monto"))
    # Soles si base_monto es "fijo"; porcentaje (0-100) si es "porcentaje_total".
    valor: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    requiere_foto: Mapped[bool] = mapped_column(default=False)
    # Desactivada: los reclamos de este tipo siempre pasan a revisión humana.
    activa: Mapped[bool] = mapped_column(default=True)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PoliticaAntifraude(Base):
    """Límites de la resolución automática. Tiene una sola fila (id = 1)."""

    __tablename__ = "politica_antifraude"
    __table_args__ = (CheckConstraint("id = 1", name="una_sola_fila"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    # Por encima de este monto, la compensación la aprueba un agente.
    monto_maximo_automatico: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # Más de esta cantidad de reclamos del cliente en el periodo: revisión humana.
    max_reclamos_periodo: Mapped[int]
    periodo_dias: Mapped[int]
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
