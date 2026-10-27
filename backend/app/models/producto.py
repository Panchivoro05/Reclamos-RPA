from decimal import Decimal

from sqlalchemy import Numeric, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pg_enum
from app.models.enums import CategoriaProducto


class Producto(Base):
    __tablename__ = "productos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    categoria: Mapped[CategoriaProducto] = mapped_column(
        pg_enum(CategoriaProducto, "categoria_producto")
    )
    precio: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    activo: Mapped[bool] = mapped_column(server_default=true(), default=True)
