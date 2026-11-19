"""Lanza el robot `resolver_reclamo.robot` y devuelve su resultado.

El worker de la fase 3 usará `resolver_reclamo()`. El robot corre en un proceso aparte:
si el navegador se cuelga, se corta por tiempo sin afectar al proceso que lo llamó.
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from bot_rpa.config import Settings

RAIZ = Path(__file__).resolve().parent.parent
ROBOT = RAIZ / "robot" / "resolver_reclamo.robot"
SOLUCIONES = ("reenvio", "reembolso_parcial", "reembolso_total", "cupon")


@dataclass(frozen=True)
class SolicitudBot:
    pedido: str
    solucion: str
    motivo: str
    monto: str = ""
    tipo_reclamo: str = ""
    # Lo que el backend sabe del pedido: el bot lo compara con lo que ve en caja.
    items_esperados: list[dict[str, Any]] = field(default_factory=list)
    total_esperado: str = ""
    # Código del reclamo (RC-2026-000001). Va al inicio del motivo en SISCAJA: si el bot se
    # reintenta y ya existe una compensación con ese código, la reutiliza en vez de duplicarla.
    reclamo: str = ""

    def __post_init__(self) -> None:
        if not re.fullmatch(r"BY-\d{6}", self.pedido):
            raise ValueError(f"Codigo de pedido invalido: {self.pedido!r}")
        if self.solucion not in SOLUCIONES:
            raise ValueError(f"Solucion invalida: {self.solucion!r}")
        if self.reclamo and not re.fullmatch(r"RC-\d{4}-\d{6}", self.reclamo):
            raise ValueError(f"Codigo de reclamo invalido: {self.reclamo!r}")

    @property
    def motivo_en_caja(self) -> str:
        """Motivo que se escribe en SISCAJA: empieza con el código del reclamo, si hay."""
        if self.reclamo and not self.motivo.startswith(f"{self.reclamo} "):
            return f"{self.reclamo} - {self.motivo}"
        return self.motivo


@dataclass
class ResultadoBot:
    exito: bool
    codigo_error: str | None
    mensaje: str
    carpeta: str
    numero_operacion: str | None = None
    monto_registrado: str | None = None
    pasos: list[dict[str, Any]] = field(default_factory=list)
    video: str | None = None
    duracion_s: float | None = None
    datos: dict[str, Any] = field(default_factory=dict)

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolver_reclamo(
    solicitud: SolicitudBot, *, visible: bool | None = None, settings: Settings | None = None
) -> ResultadoBot:
    settings = settings or Settings()
    visible = settings.visible if visible is None else visible
    momento = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    carpeta = (settings.salidas_dir / f"{momento}_{solicitud.pedido}").resolve()
    carpeta.mkdir(parents=True, exist_ok=True)

    variables = {
        "CAJA_URL": settings.caja_url.rstrip("/"),
        "OPERADOR_USUARIO": settings.operador_usuario,
        "PEDIDO": solicitud.pedido,
        "TIPO_RECLAMO": solicitud.tipo_reclamo,
        "SOLUCION": solicitud.solucion,
        "MONTO": solicitud.monto,
        "MOTIVO": solicitud.motivo_en_caja,
        "RECLAMO": solicitud.reclamo,
        "ITEMS_ESPERADOS": json.dumps(solicitud.items_esperados, ensure_ascii=False)
        if solicitud.items_esperados
        else "",
        "TOTAL_ESPERADO": solicitud.total_esperado,
        "SALIDA": str(carpeta),
        "VISIBLE": str(visible),
        # En modo visible el mouse se desliza más suave y se tipea más pausado.
        "PASOS_MOUSE": "30" if visible else "5",
        "PAUSA_TECLA": "70 ms" if visible else "10 ms",
        "VELOCIDAD_MS": str(settings.velocidad_ms),
        "GRABAR_VIDEO": str(settings.grabar_video),
    }
    comando = [sys.executable, "-m", "robot", "--outputdir", str(carpeta / "robot")]
    comando += ["--consolecolors", "off", "--console", "quiet", "--report", "NONE"]
    for nombre, valor in variables.items():
        comando += ["--variable", f"{nombre}:{valor}"]
    comando.append(str(ROBOT))

    # La clave viaja solo por el entorno del proceso: Type Secret la lee sin registrarla.
    entorno = {**os.environ, "CAJA_OPERADOR_CLAVE": settings.operador_clave}
    try:
        proceso = subprocess.run(
            comando,
            cwd=RAIZ,
            env=entorno,
            capture_output=True,
            text=True,
            timeout=settings.timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _fallo(carpeta, "tiempo_agotado", f"El bot no termino en {settings.timeout_s} s.")

    ruta_resultado = carpeta / "resultado.json"
    if not ruta_resultado.exists():
        detalle = (proceso.stderr or proceso.stdout).strip()[-500:]
        return _fallo(carpeta, "error_inesperado", f"El bot no genero resultado. {detalle}")
    return _leer(carpeta, json.loads(ruta_resultado.read_text(encoding="utf-8")))


def _leer(carpeta: Path, datos: dict[str, Any]) -> ResultadoBot:
    propios = {
        "exito",
        "codigo_error",
        "mensaje",
        "numero_operacion",
        "monto_registrado",
        "pasos",
        "video",
        "duracion_s",
    }
    return ResultadoBot(
        exito=bool(datos.get("exito")),
        codigo_error=datos.get("codigo_error"),
        mensaje=str(datos.get("mensaje", "")),
        carpeta=str(carpeta),
        numero_operacion=datos.get("numero_operacion"),
        monto_registrado=datos.get("monto_registrado"),
        pasos=list(datos.get("pasos", [])),
        video=datos.get("video"),
        duracion_s=datos.get("duracion_s"),
        datos={k: v for k, v in datos.items() if k not in propios},
    )


def _fallo(carpeta: Path, codigo: str, mensaje: str) -> ResultadoBot:
    return ResultadoBot(exito=False, codigo_error=codigo, mensaje=mensaje, carpeta=str(carpeta))
