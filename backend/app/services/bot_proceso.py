"""Ejecutor real del bot: lanza `python -m bot_rpa` en su propio entorno y lee su JSON.

El bot vive en bot-rpa/ con sus propias dependencias (Robot Framework, Playwright). El backend
no las instala: solo ejecuta el bot como un programa aparte y conversa con él por la línea de
comandos (entrada) y JSON (salida). Si el navegador se cuelga, se corta por tiempo.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Self

from app.core.config import Settings
from app.models import SolucionCompensacion
from app.services.bot import ResultadoBot, SolicitudBot

logger = logging.getLogger(__name__)

SOLUCIONES_CON_MONTO = frozenset(
    {SolucionCompensacion.REEMBOLSO_PARCIAL, SolucionCompensacion.CUPON}
)


class EjecutorBotProceso:
    def __init__(self, python: Path, carpeta_bot: Path, timeout_s: int) -> None:
        self.python = python
        self.carpeta_bot = carpeta_bot
        self.timeout_s = timeout_s

    @classmethod
    def desde_settings(cls, settings: Settings) -> Self:
        return cls(settings.bot_python, settings.worker_bot_dir, settings.worker_bot_timeout_s)

    def comando(self, solicitud: SolicitudBot) -> list[str]:
        comando = [str(self.python), "-m", "bot_rpa"]
        comando += ["--pedido", solicitud.pedido_codigo, "--solucion", solicitud.solucion.value]
        comando += ["--motivo", solicitud.motivo, "--reclamo", solicitud.reclamo_codigo]
        if solicitud.solucion in SOLUCIONES_CON_MONTO:
            comando += ["--monto", f"{solicitud.monto:.2f}"]
        if solicitud.items_esperados:
            comando += [
                "--items-esperados",
                json.dumps(solicitud.items_esperados, ensure_ascii=False),
            ]
        if solicitud.total_esperado is not None:
            comando += ["--total-esperado", f"{solicitud.total_esperado:.2f}"]
        # Visible u oculto lo decide el bot con BOT_VISIBLE (lo lee del .env de la raíz).
        return comando

    def resolver(self, solicitud: SolicitudBot) -> ResultadoBot:
        try:
            proceso = subprocess.run(
                self.comando(solicitud),
                cwd=self.carpeta_bot,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except FileNotFoundError:
            return _fallo(
                "error_inesperado",
                f"No se encontró el bot ({self.python}). Crea el entorno de bot-rpa (ver README).",
            )
        except subprocess.TimeoutExpired:
            return _fallo("tiempo_agotado", f"El bot no terminó en {self.timeout_s} s.")

        try:
            datos: dict[str, Any] = json.loads(proceso.stdout)
        except json.JSONDecodeError:
            detalle = (proceso.stderr or proceso.stdout).strip()[-500:]
            logger.error("El bot no devolvió JSON: %s", detalle)
            return _fallo("error_inesperado", f"El bot no devolvió un resultado. {detalle}")
        return resultado_desde_json(datos)


def resultado_desde_json(datos: dict[str, Any]) -> ResultadoBot:
    """Traduce el JSON de `python -m bot_rpa` (ver bot-rpa/README) al resultado del backend."""
    carpeta = datos.get("carpeta")
    return ResultadoBot(
        exito=bool(datos.get("exito")),
        codigo_error=datos.get("codigo_error"),
        mensaje=str(datos.get("mensaje", "")),
        numero_operacion=datos.get("numero_operacion"),
        duracion_s=datos.get("duracion_s"),
        pasos=list(datos.get("pasos") or []),
        carpeta=Path(carpeta) if carpeta else None,
        video=datos.get("video"),
    )


def _fallo(codigo: str, mensaje: str) -> ResultadoBot:
    return ResultadoBot(exito=False, codigo_error=codigo, mensaje=mensaje)
