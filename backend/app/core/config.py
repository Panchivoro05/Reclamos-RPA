from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthMode(StrEnum):
    DEV = "dev"
    FIREBASE = "firebase"


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

    @property
    def cors_origins_list(self) -> list[str]:
        return [origen.strip() for origen in self.cors_origins.split(",") if origen.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
