"""Análisis del reclamo antes de decidir: IA (texto y foto) y foto repetida.

Se suma a las reglas y controles antifraude de `resolucion.py` como controles adicionales:
cualquiera que falle lleva el reclamo a revisión humana, y el agente ve todos los motivos.

- ia_texto: la IA confirma, con confianza suficiente, el tipo de problema que eligió el cliente.
- ia_foto: la foto muestra comida y respalda lo que se reclama.
- foto_repetida: la misma foto (o casi igual) ya se usó en otro reclamo. No usa IA: un hash
  perceptual detecta la misma imagen aunque la hayan recomprimido o achicado.

La IA solo puede llevar a revisión humana: nunca aprueba ni decide montos.
"""

import io
import logging
from dataclasses import dataclass
from decimal import Decimal

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OperacionIA, Reclamo, TipoReclamo
from app.services.ia import (
    AnalisisFoto,
    AnalisisTexto,
    EntradaFoto,
    EntradaTexto,
    ProveedorIA,
)
from app.services.ia_registro import llamar
from app.services.resolucion import Control

logger = logging.getLogger(__name__)

TIPOS_MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}

# Bits distintos (de 64) para considerar dos fotos "la misma": tolera recompresión y cambios
# de tamaño, pero no fotos distintas del mismo producto.
DISTANCIA_MAXIMA_FOTO = 6


@dataclass(frozen=True)
class EntradasIA:
    """Lo que se le envía a la IA, armado mientras el reclamo está bloqueado."""

    texto: EntradaTexto
    foto: EntradaFoto | None


@dataclass(frozen=True)
class AnalisisIA:
    texto: AnalisisTexto
    foto: AnalisisFoto | None


def preparar_entradas(reclamo: Reclamo, foto: bytes | None) -> EntradasIA:
    """Solo datos del reclamo: nunca el nombre, el correo ni el teléfono del cliente."""
    reclamados = [
        f"{item.cantidad_afectada} x {item.pedido_item.producto.nombre}" for item in reclamo.items
    ]
    texto = EntradaTexto(
        descripcion=reclamo.descripcion,
        tipo_elegido=reclamo.tipo,
        productos_pedido=[item.producto.nombre for item in reclamo.pedido.items],
        productos_reclamados=reclamados,
    )
    entrada_foto = None
    if foto and reclamo.foto_ruta:
        extension = reclamo.foto_ruta.rsplit(".", 1)[-1]
        entrada_foto = EntradaFoto(
            contenido=foto,
            tipo_mime=TIPOS_MIME.get(extension, "image/jpeg"),
            tipo_elegido=reclamo.tipo,
            descripcion=reclamo.descripcion,
            productos_reclamados=reclamados,
        )
    return EntradasIA(texto, entrada_foto)


def analizar_con_ia(
    session: Session, reclamo_id: int, entradas: EntradasIA, proveedor: ProveedorIA
) -> AnalisisIA:
    """Llama a la IA y registra cada llamada. Lanza ErrorIA si alguna falla (se reintenta)."""
    texto = llamar(
        session,
        OperacionIA.CLASIFICAR_TEXTO,
        proveedor.nombre,
        lambda: proveedor.clasificar_texto(entradas.texto),
        reclamo_id=reclamo_id,
    )
    foto = None
    if entradas.foto is not None:
        entrada_foto = entradas.foto
        foto = llamar(
            session,
            OperacionIA.ANALIZAR_FOTO,
            proveedor.nombre,
            lambda: proveedor.analizar_foto(entrada_foto),
            reclamo_id=reclamo_id,
        )
    return AnalisisIA(texto, foto)


def controles_ia(tipo: TipoReclamo, analisis: AnalisisIA, umbral: Decimal) -> list[Control]:
    """Convierte la opinión de la IA en controles (función pura: se prueba sin IA ni base)."""
    controles = [_control_texto(tipo, analisis.texto, float(umbral))]
    if analisis.foto is not None:
        controles.append(_control_foto(analisis.foto, float(umbral)))
    return controles


def _control_texto(tipo: TipoReclamo, texto: AnalisisTexto, umbral: float) -> Control:
    confianza = f"confianza {texto.confianza:.2f}"
    if texto.tipo_detectado is None or texto.confianza < umbral:
        return Control(
            "ia_texto",
            False,
            f"La IA no pudo confirmar el problema descrito ({confianza}, mínimo {umbral:.2f}): "
            f"{texto.explicacion}",
        )
    if texto.tipo_detectado is not tipo:
        return Control(
            "ia_texto",
            False,
            f"Según la IA, la descripción corresponde a {texto.tipo_detectado.value} y no a "
            f"{tipo.value} ({confianza}): {texto.explicacion}",
        )
    return Control("ia_texto", True, f"La IA confirma el tipo {tipo.value} ({confianza})")


def _control_foto(foto: AnalisisFoto, umbral: float) -> Control:
    confianza = f"confianza {foto.confianza:.2f}"
    if not foto.es_comida:
        return Control(
            "ia_foto", False, f"La foto no muestra comida ni un pedido: {foto.descripcion}"
        )
    if not foto.coherente or foto.confianza < umbral:
        return Control(
            "ia_foto",
            False,
            f"La foto no respalda el reclamo ({confianza}): {foto.descripcion}",
        )
    return Control("ia_foto", True, f"La foto respalda el reclamo ({confianza})")


# ---------- Foto repetida (hash perceptual) ----------


def hash_foto(contenido: bytes) -> str | None:
    """dHash de 64 bits en hexadecimal: compara el brillo de píxeles vecinos en una miniatura
    de 9x8 en grises. Fotos iguales (aunque recomprimidas o achicadas) dan hashes casi iguales.
    """
    try:
        with Image.open(io.BytesIO(contenido)) as imagen:
            pixeles = list(imagen.convert("L").resize((9, 8), Image.Resampling.LANCZOS).getdata())
    except (UnidentifiedImageError, OSError, ValueError):
        logger.warning("No se pudo calcular el hash de una foto (formato no reconocido)")
        return None
    bits = 0
    for fila in range(8):
        for columna in range(8):
            izquierda = pixeles[fila * 9 + columna]
            derecha = pixeles[fila * 9 + columna + 1]
            bits = (bits << 1) | (izquierda > derecha)
    return f"{bits:016x}"


def distancia(hash_a: str, hash_b: str) -> int:
    """Cantidad de bits distintos entre dos hashes (distancia de Hamming)."""
    return (int(hash_a, 16) ^ int(hash_b, 16)).bit_count()


def reclamo_con_la_misma_foto(session: Session, reclamo: Reclamo) -> str | None:
    """Código de otro reclamo (de cualquier cliente) con la misma foto, o None.

    Se comparan en Python todos los hashes guardados: alcanza para miles de reclamos. Con
    millones, se usaría un índice para distancia de Hamming (por ejemplo, un BK-tree).
    """
    if reclamo.foto_hash is None:
        return None
    otros = session.execute(
        select(Reclamo.codigo, Reclamo.foto_hash).where(
            Reclamo.id != reclamo.id, Reclamo.foto_hash.is_not(None)
        )
    )
    for codigo, otro_hash in otros:
        if distancia(reclamo.foto_hash, otro_hash) <= DISTANCIA_MAXIMA_FOTO:
            return codigo
    return None


def control_foto_repetida(codigo_repetido: str | None) -> Control:
    if codigo_repetido:
        return Control(
            "foto_repetida",
            False,
            f"La foto es igual (o casi igual) a la del reclamo {codigo_repetido}",
        )
    return Control("foto_repetida", True, "La foto no se usó en otros reclamos")
