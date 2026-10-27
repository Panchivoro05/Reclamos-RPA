from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Nombres de restricciones predecibles: Alembic genera migraciones estables.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def pg_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """Enum de PostgreSQL que guarda el valor ('en_camino'), no el nombre ('EN_CAMINO')."""
    return Enum(
        enum_cls,
        name=name,
        values_callable=lambda cls: [miembro.value for miembro in cls],
        validate_strings=True,
    )


def creado_en_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
