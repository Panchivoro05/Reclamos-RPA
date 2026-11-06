"""Configuración del bot, leída de variables de entorno (y del .env de la raíz si existe)."""

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BOT_",
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # SISCAJA y el operador con el que el bot inicia sesión (las mismas variables de caja).
    caja_url: str = Field(
        default="http://127.0.0.1:5050", validation_alias=AliasChoices("BOT_CAJA_URL", "CAJA_URL")
    )
    operador_usuario: str = Field(
        default="cajero01",
        validation_alias=AliasChoices("BOT_OPERADOR_USUARIO", "CAJA_OPERADOR_USUARIO"),
    )
    operador_clave: str = Field(
        default="", validation_alias=AliasChoices("BOT_OPERADOR_CLAVE", "CAJA_OPERADOR_CLAVE")
    )

    # Carpeta donde cada ejecución deja resultado.json, capturas, video y log de Robot.
    salidas_dir: Path = Path("./salidas")
    # true: navegador visible y en cámara lenta (demo). false: oculto (worker).
    visible: bool = False
    # Pausa de Playwright entre acciones en modo visible (milisegundos).
    velocidad_ms: int = 250
    grabar_video: bool = True
    # Tiempo máximo de una ejecución completa.
    timeout_s: int = 180
