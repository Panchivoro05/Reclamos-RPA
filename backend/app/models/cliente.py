from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, creado_en_column


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    firebase_uid: Mapped[str | None] = mapped_column(String(128), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    telefono_whatsapp: Mapped[str | None] = mapped_column(String(20))
    creado_en: Mapped[datetime] = creado_en_column()
