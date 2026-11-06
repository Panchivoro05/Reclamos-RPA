"""Configuración de SISCAJA, leída de variables de entorno (y del .env de la raíz si existe)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CAJA_",
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: Path = Path("./data/caja.db")
    # Firma la cookie de sesión. Si está vacía se genera una al azar en cada arranque
    # (las sesiones se pierden al reiniciar, lo que en desarrollo no importa).
    secret_key: str = ""

    # Operador que crea `flask --app caja init-db`. La clave nunca va en el repositorio.
    operador_usuario: str = "cajero01"
    operador_nombre: str = "Cajero de turno"
    operador_clave: str = ""
