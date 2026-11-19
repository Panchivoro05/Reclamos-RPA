"""Interfaz con el bot RPA.

El worker no sabe CÓMO se ejecuta el bot: solo le pasa una `SolicitudBot` y recibe un
`ResultadoBot`. Así las pruebas usan `EjecutorBotSimulado` (sin navegador ni SISCAJA) y el
worker real usa `EjecutorBotProceso` (bloque 4), que lanza `python -m bot_rpa`.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from app.models import SolucionCompensacion

# Errores ajenos al negocio: vale la pena reintentar (caja caída, navegador colgado...).
ERRORES_TECNICOS = frozenset({"tiempo_agotado", "error_inesperado", "credenciales_invalidas"})


@dataclass(frozen=True)
class SolicitudBot:
    reclamo_codigo: str
    pedido_codigo: str
    solucion: SolucionCompensacion
    monto: Decimal
    motivo: str
    # Lo que el backend sabe del pedido; el bot lo compara con lo que ve en caja.
    items_esperados: list[dict[str, Any]] = field(default_factory=list)
    total_esperado: Decimal | None = None


@dataclass(frozen=True)
class ResultadoBot:
    exito: bool
    codigo_error: str | None
    mensaje: str
    numero_operacion: str | None = None
    duracion_s: float | None = None
    pasos: list[dict[str, Any]] = field(default_factory=list)
    # Carpeta de la ejecución (capturas, video, resultado.json), si el bot la generó.
    carpeta: Path | None = None
    video: str | None = None

    @property
    def es_error_tecnico(self) -> bool:
        return not self.exito and self.codigo_error in ERRORES_TECNICOS


class EjecutorBot(Protocol):
    def resolver(self, solicitud: SolicitudBot) -> ResultadoBot: ...


class EjecutorBotSimulado:
    """Bot de mentira para pruebas y demos sin SISCAJA.

    Por defecto siempre registra la compensación. Se le puede pasar una lista de resultados
    (uno por llamada) o una función que decida según la solicitud.
    """

    def __init__(
        self,
        resultados: list[ResultadoBot] | Callable[[SolicitudBot], ResultadoBot] | None = None,
    ) -> None:
        self._resultados = resultados
        self.solicitudes: list[SolicitudBot] = []

    def resolver(self, solicitud: SolicitudBot) -> ResultadoBot:
        self.solicitudes.append(solicitud)
        if callable(self._resultados):
            return self._resultados(solicitud)
        if self._resultados:
            return self._resultados.pop(0)
        numero = f"CMP-{len(self.solicitudes):06d}"
        return ResultadoBot(
            exito=True,
            codigo_error=None,
            mensaje="Compensacion registrada en SISCAJA (simulado).",
            numero_operacion=numero,
            duracion_s=0.1,
        )
