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


class PushModo(StrEnum):
    EXPO = "expo"  # Expo Push Service (llega al celular por FCM)
    FALSO = "falso"  # solo se registra en el log (pruebas y desarrollo sin celular)


class IAModo(StrEnum):
    SIMULADO = "simulado"  # reglas de palabras clave: pruebas y demos sin internet
    GEMINI = "gemini"  # API de Gemini (necesita GEMINI_API_KEY)


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

    # ---------- Notificaciones (fase 4) ----------
    push_modo: PushModo = PushModo.FALSO
    expo_push_url: str = "https://exp.host/--/api/v2/push/send"
    # Opcional: solo si en expo.dev se activa "Enhanced Security for Push Notifications".
    expo_access_token: str = ""

    # ---------- Inteligencia artificial (fase 5) ----------
    ia_modo: IAModo = IAModo.SIMULADO
    # Clave de Google AI Studio (aistudio.google.com). Secreta: solo en el .env.
    gemini_api_key: str = ""
    # Estable, multimodal (texto e imagen) y el más económico de la línea actual.
    ia_modelo: str = "gemini-3.5-flash-lite"
    # Con alta demanda, Gemini llegó a tardar ~60 s en responder (medido en desarrollo).
    ia_timeout_s: float = 60
    # Redactar un mensaje no puede demorar el reclamo: si tarda más, se usa la plantilla.
    ia_timeout_mensaje_s: float = 15
    # Precio del modelo en USD por millón de tokens: solo para estimar el costo de cada llamada.
    # Valores de gemini-3.5-flash-lite (plan de pago); en el plan gratuito no se cobra.
    ia_precio_entrada_usd_millon: float = 0.30
    ia_precio_salida_usd_millon: float = 2.50

    @property
    def bot_python(self) -> Path:
        return self.worker_bot_python or self.worker_bot_dir / ".venv" / "bin" / "python"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origen.strip() for origen in self.cors_origins.split(",") if origen.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
