"""Copia la evidencia de una ejecución del bot (capturas, video y resultado) al almacenamiento.

Queda en evidencias/<reclamo>/intento-<n>/ y se asocia al reclamo en `ejecuciones_bot`.
Así no depende de la carpeta de salidas del bot, que se puede limpiar.
"""

import logging
from dataclasses import dataclass

from app.services.almacenamiento import PATRON_EVIDENCIA, AlmacenamientoArchivos
from app.services.bot import ResultadoBot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvidenciaGuardada:
    carpeta: str  # evidencias/RC-2026-000001/intento-1
    video: str | None  # evidencias/RC-2026-000001/intento-1/video.webm


def guardar_evidencia(
    almacenamiento: AlmacenamientoArchivos,
    resultado: ResultadoBot,
    reclamo_codigo: str,
    intento: int,
) -> EvidenciaGuardada | None:
    origen = resultado.carpeta
    if origen is None or not origen.is_dir():
        return None
    destino = f"evidencias/{reclamo_codigo}/intento-{intento}"
    archivos = [origen / "resultado.json", origen / "video.webm"]
    archivos += sorted((origen / "capturas").glob("*.png"))

    video = None
    for archivo in archivos:
        if not archivo.is_file():
            continue
        relativa = archivo.relative_to(origen).as_posix()
        ruta = f"{destino}/{relativa}"
        if not PATRON_EVIDENCIA.match(ruta):
            logger.warning("Evidencia ignorada (nombre inesperado): %s", relativa)
            continue
        almacenamiento.guardar_evidencia(ruta, archivo.read_bytes())
        if relativa == "video.webm":
            video = ruta
    return EvidenciaGuardada(carpeta=destino, video=video)
