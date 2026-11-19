"""Interfaz con la inteligencia artificial.

El worker no sabe QUÉ IA usa: le pasa al `ProveedorIA` los datos del reclamo y recibe un
resultado ya validado (modelos Pydantic). Así se puede cambiar Gemini por otro proveedor sin
tocar las reglas, y las pruebas usan `ProveedorSimulado` (sin internet ni clave).

La IA solo opina: el código decide qué hacer con su opinión (escalar o seguir). Nunca decide
montos ni aprueba un reclamo por su cuenta.
"""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field

from app.core.config import IAModo, get_settings
from app.models import EstadoReclamo, TipoReclamo


class ErrorIA(Exception):
    """Falla técnica (red, cuota agotada, respuesta inválida): vale la pena reintentar."""


# ---------- Lo que se le pide ----------


@dataclass(frozen=True)
class EntradaTexto:
    """Solo datos del reclamo: nunca el nombre, el correo ni el teléfono del cliente."""

    descripcion: str
    tipo_elegido: TipoReclamo
    productos_pedido: list[str]  # nombres de los productos del pedido
    productos_reclamados: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EntradaFoto:
    contenido: bytes
    tipo_mime: str  # image/jpeg, image/png...
    tipo_elegido: TipoReclamo
    descripcion: str
    productos_reclamados: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EntradaMensaje:
    """Para redactar el mensaje de un hito. `mensaje_base` es la plantilla con los datos
    correctos: la IA solo puede reescribirla, nunca agregar datos (lo verifica `mensajes.py`).
    No lleva el motivo interno de un escalamiento: el cliente no debe verlo."""

    estado: EstadoReclamo
    tipo: TipoReclamo
    productos_reclamados: list[str]
    mensaje_base: str


# ---------- Lo que responde (validado) ----------


class AnalisisTexto(BaseModel):
    """Clasificación de la descripción que escribió el cliente."""

    # None si la descripción no permite saber de qué se queja.
    tipo_detectado: TipoReclamo | None
    productos_mencionados: list[str] = Field(default_factory=list)
    confianza: float = Field(ge=0, le=1)
    explicacion: str = Field(description="Una frase para el agente humano")


class AnalisisFoto(BaseModel):
    """¿La foto respalda lo que se reclama?"""

    es_comida: bool
    coherente: bool  # la foto muestra lo que el cliente describe
    descripcion: str = Field(description="Qué se ve en la foto, en una frase")
    confianza: float = Field(ge=0, le=1)


class MensajeRedactado(BaseModel):
    mensaje: str = Field(description="El mensaje para el cliente, en una o dos frases")


@dataclass(frozen=True)
class Uso:
    """Consumo de una llamada (para el registro de costo)."""

    modelo: str
    tokens_entrada: int = 0
    tokens_salida: int = 0


@dataclass(frozen=True)
class RespuestaIA[T: BaseModel]:
    resultado: T
    uso: Uso


class ProveedorIA(Protocol):
    nombre: str

    def clasificar_texto(self, entrada: EntradaTexto) -> RespuestaIA[AnalisisTexto]: ...

    def analizar_foto(self, entrada: EntradaFoto) -> RespuestaIA[AnalisisFoto]: ...

    def redactar_mensaje(self, entrada: EntradaMensaje) -> RespuestaIA[MensajeRedactado]: ...


# ---------- Proveedor simulado ----------


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes: "Llegó FRÍA" → "llego fria"."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower()


# Comienzos de palabra que delatan cada tipo (expresiones regulares sobre el texto normalizado;
# se buscan al inicio de una palabra: "fria" sí, "frita" no).
PALABRAS_CLAVE: dict[TipoReclamo, tuple[str, ...]] = {
    TipoReclamo.PRODUCTO_EQUIVOCADO: (
        "equivocad",
        "otro producto",
        "en vez de",
        "en lugar de",
        "no es lo que",
        "no era lo que",
        "me trajeron otr",
        "cambiad",
        "distint",
    ),
    TipoReclamo.PEDIDO_INCOMPLETO: (
        "falt",
        "incomplet",
        "no vino",
        "no venia",
        "no llego",
        "no trajeron",
        "no estaba",
        "solo trajeron",
    ),
    TipoReclamo.MAL_ESTADO: (
        "mal estado",
        r"fri[ao]s?\b",
        "podrid",
        "quemad",
        "crud",
        "vencid",
        "pelo",
        "derramad",
        "aplastad",
        "malogr",
        "olor",
    ),
    TipoReclamo.DEMORA: (
        "demor",
        "tard[oe]",
        "espere",
        "esperando",
        r"horas?\b",
        "nunca llego",
    ),
}


class ProveedorSimulado:
    """IA de mentira y determinista: palabras clave en vez de un modelo.

    Sirve para las pruebas y para demos sin internet. Se le pueden pasar funciones que
    decidan la respuesta (o lancen `ErrorIA`) para probar cada caso.
    """

    nombre = "simulado"
    modelo = "palabras-clave"

    def __init__(
        self,
        texto: Callable[[EntradaTexto], AnalisisTexto] | None = None,
        foto: Callable[[EntradaFoto], AnalisisFoto] | None = None,
        mensaje: Callable[[EntradaMensaje], MensajeRedactado] | None = None,
    ) -> None:
        self._texto = texto
        self._foto = foto
        self._mensaje = mensaje
        self.entradas_texto: list[EntradaTexto] = []
        self.entradas_foto: list[EntradaFoto] = []
        self.entradas_mensaje: list[EntradaMensaje] = []

    def clasificar_texto(self, entrada: EntradaTexto) -> RespuestaIA[AnalisisTexto]:
        self.entradas_texto.append(entrada)
        analisis = self._texto(entrada) if self._texto else clasificar_por_palabras(entrada)
        return RespuestaIA(analisis, self._uso(entrada.descripcion))

    def analizar_foto(self, entrada: EntradaFoto) -> RespuestaIA[AnalisisFoto]:
        self.entradas_foto.append(entrada)
        analisis = (
            self._foto(entrada)
            if self._foto
            else AnalisisFoto(
                es_comida=True,
                coherente=True,
                descripcion="Foto de comida (análisis simulado).",
                confianza=0.9,
            )
        )
        return RespuestaIA(analisis, self._uso(entrada.descripcion))

    def redactar_mensaje(self, entrada: EntradaMensaje) -> RespuestaIA[MensajeRedactado]:
        self.entradas_mensaje.append(entrada)
        if self._mensaje:
            redactado = self._mensaje(entrada)
        else:
            saludo = SALUDOS_SIMULADOS.get(entrada.estado, "")
            redactado = MensajeRedactado(mensaje=f"{saludo} {entrada.mensaje_base}".strip())
        return RespuestaIA(redactado, self._uso(entrada.mensaje_base))

    def _uso(self, texto: str) -> Uso:
        # Aproximación de tokens (≈ 4 caracteres por token) para que el registro tenga datos.
        return Uso(self.modelo, tokens_entrada=len(texto) // 4 + 50, tokens_salida=40)


SALUDOS_SIMULADOS = {
    EstadoReclamo.VALIDADO: "¡Buenas noticias!",
    EstadoReclamo.RESUELTO: "¡Gracias por tu paciencia!",
    EstadoReclamo.ESCALADO: "Lamentamos el inconveniente.",
}


def clasificar_por_palabras(entrada: EntradaTexto) -> AnalisisTexto:
    texto = normalizar(entrada.descripcion)
    aciertos = {
        tipo: sum(1 for palabra in palabras if re.search(rf"\b{palabra}", texto))
        for tipo, palabras in PALABRAS_CLAVE.items()
    }
    mayor = max(aciertos.values())
    ganadores = [tipo for tipo, n in aciertos.items() if n == mayor]
    mencionados = [p for p in entrada.productos_pedido if _menciona(texto, normalizar(p))]
    if mayor == 0:
        return AnalisisTexto(
            tipo_detectado=None,
            productos_mencionados=mencionados,
            confianza=0.3,
            explicacion="La descripción no dice con claridad cuál es el problema.",
        )
    if len(ganadores) > 1:
        # Empate: se queda con el que eligió el cliente si está entre los empatados.
        tipo = entrada.tipo_elegido if entrada.tipo_elegido in ganadores else ganadores[0]
        return AnalisisTexto(
            tipo_detectado=tipo,
            productos_mencionados=mencionados,
            confianza=0.6,
            explicacion="La descripción menciona más de un tipo de problema.",
        )
    return AnalisisTexto(
        tipo_detectado=ganadores[0],
        productos_mencionados=mencionados,
        confianza=0.9,
        explicacion=f"La descripción corresponde a {ganadores[0].value}.",
    )


def _menciona(texto: str, producto: str) -> bool:
    """El producto aparece en el texto (por su nombre o por su primera palabra significativa)."""
    if producto in texto:
        return True
    palabras = [p for p in re.findall(r"[a-z]+", producto) if len(p) > 3]
    return bool(palabras) and palabras[0] in texto


def get_proveedor_ia() -> ProveedorIA:
    settings = get_settings()
    match settings.ia_modo:
        case IAModo.SIMULADO:
            return ProveedorSimulado()
        case IAModo.GEMINI:
            # Import diferido: sin IA_MODO=gemini no se carga el SDK.
            from app.services.ia_gemini import ProveedorGemini

            return ProveedorGemini(
                settings.gemini_api_key,
                settings.ia_modelo,
                timeout_s=settings.ia_timeout_s,
                timeout_mensaje_s=settings.ia_timeout_mensaje_s,
            )
