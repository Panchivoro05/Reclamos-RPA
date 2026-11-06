"""Librería de Robot Framework con la lógica del bot que no es de navegador.

Lleva el registro de pasos y capturas, compara lo que se ve en pantalla con lo esperado y
escribe `resultado.json`, el contrato que leerá el worker de la fase 3.
"""

import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from importlib import resources
from pathlib import Path
from typing import Any

from robot.api import logger
from robot.api.deco import keyword, library

PATRON_ERROR = re.compile(r"^\[(?P<codigo>[a-z_]+)\]\s*(?P<mensaje>.*)$", re.DOTALL)


class ErrorBot(AssertionError):
    """Error de negocio del bot. Robot muestra el mensaje como '[codigo] mensaje'."""

    ROBOT_SUPPRESS_NAME = True

    def __init__(self, codigo: str, mensaje: str) -> None:
        super().__init__(f"[{codigo}] {mensaje}")


def a_centimos(texto: str) -> int:
    """'S/ 1,234.50' → 123450."""
    limpio = texto.strip().upper().removeprefix("S/").strip().replace(",", "")
    try:
        return int(Decimal(limpio) * 100)
    except InvalidOperation:
        raise ValueError(f"No es un monto: {texto!r}") from None


def ahora_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@library(scope="SUITE", auto_keywords=False)
class BotRPA:
    def __init__(self) -> None:
        self.carpeta = Path(".")
        self.datos: dict[str, Any] = {}
        self.pasos: list[dict[str, Any]] = []

    @keyword
    def iniciar_resultado(self, carpeta: str, **datos: str) -> None:
        self.carpeta = Path(carpeta)
        (self.carpeta / "capturas").mkdir(parents=True, exist_ok=True)
        self.datos = {**datos, "inicio": ahora_iso()}
        self.pasos = []

    @keyword
    def script_del_cursor(self) -> str:
        texto = resources.files("bot_rpa").joinpath("cursor.js").read_text(encoding="utf-8")
        # Browser reconoce una función solo si el texto empieza con ella: se quitan los
        # comentarios de cabecera.
        return texto[texto.index("() => {") :]

    @keyword
    def ruta_de_captura(self, nombre: str) -> str:
        numero = len(self.pasos) + 1
        return str(self.carpeta / "capturas" / f"{numero:02d}_{nombre}")

    @keyword
    def registrar_paso(self, paso: str, descripcion: str, captura: str | None = None) -> None:
        self.pasos.append(
            {
                "paso": paso,
                "descripcion": descripcion,
                "captura": self._relativa(captura) if captura else None,
                "momento": ahora_iso(),
            }
        )

    @keyword
    def ultimo_paso(self) -> str:
        return self.pasos[-1]["paso"] if self.pasos else ""

    @keyword
    def guardar_dato(self, nombre: str, valor: str) -> None:
        self.datos[nombre] = valor

    @keyword
    def fallar_con_codigo(self, codigo: str, mensaje: str) -> None:
        raise ErrorBot(codigo, mensaje)

    @keyword
    def verificar_total(self, total_en_pantalla: str, total_esperado: str) -> None:
        if not total_esperado:
            logger.info("Sin total esperado: no se compara.")
            return
        if a_centimos(total_en_pantalla) != a_centimos(total_esperado):
            raise ErrorBot(
                "datos_no_coinciden",
                f"El total en caja es {total_en_pantalla} y el esperado S/ "
                f"{a_centimos(total_esperado) / 100:.2f}.",
            )

    @keyword
    def verificar_items(self, items_en_pantalla: list[dict[str, Any]], esperados_json: str) -> None:
        """Cada producto esperado debe estar en el pedido con al menos esa cantidad."""
        if not esperados_json:
            logger.info("Sin ítems esperados: no se comparan.")
            return
        en_pantalla: dict[str, int] = {}
        for item in items_en_pantalla:
            nombre = str(item["producto"]).strip().casefold()
            en_pantalla[nombre] = en_pantalla.get(nombre, 0) + int(item["cantidad"])
        faltantes = []
        for esperado in json.loads(esperados_json):
            nombre = str(esperado["producto"]).strip()
            cantidad = int(esperado.get("cantidad", 1))
            if en_pantalla.get(nombre.casefold(), 0) < cantidad:
                faltantes.append(f"{cantidad} x {nombre}")
        if faltantes:
            raise ErrorBot(
                "datos_no_coinciden",
                "El pedido en caja no tiene: " + ", ".join(faltantes) + ".",
            )

    @keyword
    def finalizar_resultado(self, estado: str, mensaje: str) -> str:
        """Escribe resultado.json a partir del estado de la tarea de Robot."""
        exito = estado == "PASS"
        codigo_error = None
        if not exito:
            encontrado = PATRON_ERROR.match(mensaje)
            if encontrado:
                codigo_error, mensaje = encontrado["codigo"], encontrado["mensaje"]
            else:
                codigo_error = "error_inesperado"
        fin = datetime.now(UTC)
        inicio = datetime.fromisoformat(self.datos.pop("inicio"))
        video = self._ordenar_video()
        resultado = {
            "exito": exito,
            "codigo_error": codigo_error,
            "mensaje": "Compensacion registrada en SISCAJA." if exito else mensaje,
            **self.datos,
            "pasos": self.pasos,
            "video": self._relativa(str(video)) if video else None,
            "inicio": inicio.isoformat(timespec="seconds"),
            "fin": fin.isoformat(timespec="seconds"),
            "duracion_s": round((fin - inicio).total_seconds(), 1),
        }
        ruta = self.carpeta / "resultado.json"
        ruta.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(ruta)

    def _ordenar_video(self) -> Path | None:
        """Playwright guarda el video con un nombre al azar: se deja como video.webm."""
        carpeta_video = self.carpeta / "video"
        grabado = next(iter(sorted(carpeta_video.glob("*.webm"))), None)
        if grabado is None:
            return None
        destino = self.carpeta / "video.webm"
        grabado.replace(destino)
        if not any(carpeta_video.iterdir()):
            carpeta_video.rmdir()
        return destino

    def _relativa(self, ruta: str) -> str:
        """Rutas relativas a la carpeta de la ejecución (se puede mover sin romperse)."""
        camino = Path(ruta)
        if not camino.suffix:  # Take Screenshot agrega .png al nombre
            camino = camino.with_suffix(".png")
        try:
            return str(camino.resolve().relative_to(self.carpeta.resolve()))
        except ValueError:
            return str(camino)
