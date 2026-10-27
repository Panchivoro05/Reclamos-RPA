"""Errores de la aplicación.

Los servicios lanzan estas excepciones con un mensaje pensado para el cliente y un
código estable que la app puede usar para decidir qué mostrar. El manejador de
app/main.py las convierte en la respuesta HTTP: {"detail": ..., "codigo": ...}.
"""

from typing import ClassVar


class ErrorAPI(Exception):
    status_code: ClassVar[int] = 400

    def __init__(self, codigo: str, mensaje: str) -> None:
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


class DatosInvalidos(ErrorAPI):
    """La petición está mal formada (JSON roto, archivo que no es imagen...)."""

    status_code = 400


class NoAutenticado(ErrorAPI):
    status_code = 401


class NoEncontrado(ErrorAPI):
    status_code = 404


class Conflicto(ErrorAPI):
    """Choca con el estado actual de los datos (por ejemplo, un reclamo duplicado)."""

    status_code = 409


class ArchivoMuyGrande(ErrorAPI):
    status_code = 413


class ReglaNegocio(ErrorAPI):
    """La petición es válida en forma, pero no cumple una regla del negocio."""

    status_code = 422
