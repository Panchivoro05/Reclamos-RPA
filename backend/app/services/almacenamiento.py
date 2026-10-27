"""Almacenamiento de las fotos de los reclamos.

El resto del sistema solo conoce la interfaz AlmacenamientoArchivos y guarda en la
base de datos el nombre que devuelve guardar(). Para pasar a Firebase Storage basta
con otra implementación y cambiar get_almacenamiento().
"""

import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings

# Nombres que genera guardar(): 32 caracteres hexadecimales y la extensión.
# Validarlos impide que un nombre como "../../.env" salga de la carpeta.
PATRON_NOMBRE = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp)$")


class AlmacenamientoArchivos(Protocol):
    def guardar(self, contenido: bytes, extension: str) -> str:
        """Guarda el archivo y devuelve el nombre con el que se recupera."""
        ...

    def leer(self, nombre: str) -> bytes | None: ...

    def eliminar(self, nombre: str) -> None: ...


class AlmacenamientoLocal:
    def __init__(self, carpeta: Path) -> None:
        self.carpeta = carpeta

    def guardar(self, contenido: bytes, extension: str) -> str:
        self.carpeta.mkdir(parents=True, exist_ok=True)
        nombre = f"{uuid.uuid4().hex}.{extension}"
        (self.carpeta / nombre).write_bytes(contenido)
        return nombre

    def leer(self, nombre: str) -> bytes | None:
        if not PATRON_NOMBRE.match(nombre):
            return None
        ruta = self.carpeta / nombre
        return ruta.read_bytes() if ruta.is_file() else None

    def eliminar(self, nombre: str) -> None:
        if PATRON_NOMBRE.match(nombre):
            (self.carpeta / nombre).unlink(missing_ok=True)


@lru_cache
def get_almacenamiento() -> AlmacenamientoArchivos:
    return AlmacenamientoLocal(get_settings().upload_dir)
