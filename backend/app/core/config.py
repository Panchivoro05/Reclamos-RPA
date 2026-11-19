from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_REPO = Path(__file__).resolve().parents[3]


class AuthMode(StrEnum):
    DEV = "dev"
    FIREBASE = "firebase"


class BotModo(StrEnum):
    PROCESO = "proceso"
    SIMULADO = "simulado"


class Settings(BaseSettings):
    """Configuración leída de variables de entorno (y del .env de la raíz si existe)."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://reclamos:reclamos_dev@127.0.0.1:5432/reclamos"
    valkey_url: str = "redis://127.0.0.1:6379/0"

    auth_mode: AuthMode = AuthMode.DEV
    firebase_credentials_path: str = ""

    reclamo_plazo_horas: int = 24
    upload_dir: Path = Path("./uploads")
    foto_max_bytes: int = 5 * 1024 * 1024
    cors_origins: str = "*"

    # ---------- Worker (fase 3) ----------
    # Reintentos del bot ante errores técnicos (caja caída, tiempo agotado) antes de escalar.
    worker_reintentos: int = 2
    # Espera antes del primer reintento; se duplica en cada intento (30 s, 60 s...).
    worker_espera_reintento_s: int = 30
    # "proceso": lanza el bot real (bot-rpa). "simulado": registra sin SISCAJA (demos y pruebas).
    bot_modo: BotModo = BotModo.PROCESO
    # Dónde está el bot (bot-rpa/) y con qué Python se ejecuta (su propio entorno virtual).
    worker_bot_dir: Path = RAIZ_REPO / "bot-rpa"
    worker_bot_python: Path | None = None  # por defecto: <worker_bot_dir>/.venv/bin/python
    # Tiempo máximo de una ejecución del bot (el bot tiene su propio límite de 180 s).
    worker_bot_timeout_s: int = 240

    @property
    def bot_python(self) -> Path:
        return self.worker_bot_python or self.worker_bot_dir / ".venv" / "bin" / "python"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origen.strip() for origen in self.cors_origins.split(",") if origen.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
