"""Envío de notificaciones push con Expo Push Service.

La app obtiene un token de Expo (ExponentPushToken[...]) y el backend le envía los avisos a
Expo por HTTPS; Expo los entrega al celular por FCM (Android) o APNs (iOS). Así el backend no
maneja credenciales de Firebase ni de Apple: esas viven en EAS (ver README).

`PushFalso` no envía nada: se usa en las pruebas y en desarrollo sin celular (PUSH_MODO=falso).
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import PushModo, get_settings

logger = logging.getLogger(__name__)

# Expo acepta hasta 100 mensajes por petición.
LOTE_MAXIMO = 100


class ErrorEnvio(Exception):
    """Falla técnica (red, Expo caído): la tarea vuelve a intentar más tarde."""


@dataclass(frozen=True)
class MensajePush:
    token: str
    titulo: str
    cuerpo: str
    datos: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ResultadoPush:
    token: str
    ok: bool
    error: str | None = None  # p. ej. "DeviceNotRegistered": la app ya no está en el celular
    mensaje: str = ""

    @property
    def token_invalido(self) -> bool:
        return self.error == "DeviceNotRegistered"


class NotificadorPush(Protocol):
    def enviar(self, mensajes: list[MensajePush]) -> list[ResultadoPush]: ...


class PushFalso:
    def __init__(self, errores: dict[str, str] | None = None) -> None:
        self.enviados: list[MensajePush] = []
        self.errores = errores or {}  # token → código de error que "devuelve Expo"

    def enviar(self, mensajes: list[MensajePush]) -> list[ResultadoPush]:
        self.enviados.extend(mensajes)
        for mensaje in mensajes:
            logger.info("[push falso] %s: %s — %s", mensaje.token, mensaje.titulo, mensaje.cuerpo)
        return [
            ResultadoPush(m.token, ok=False, error=self.errores[m.token])
            if m.token in self.errores
            else ResultadoPush(m.token, ok=True)
            for m in mensajes
        ]


class PushExpo:
    def __init__(
        self, url: str, access_token: str = "", cliente: httpx.Client | None = None
    ) -> None:
        self.url = url
        self.access_token = access_token
        self.cliente = cliente or httpx.Client(timeout=10)

    def enviar(self, mensajes: list[MensajePush]) -> list[ResultadoPush]:
        resultados: list[ResultadoPush] = []
        for inicio in range(0, len(mensajes), LOTE_MAXIMO):
            resultados += self._enviar_lote(mensajes[inicio : inicio + LOTE_MAXIMO])
        return resultados

    def _enviar_lote(self, lote: list[MensajePush]) -> list[ResultadoPush]:
        encabezados = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.access_token:
            encabezados["Authorization"] = f"Bearer {self.access_token}"
        cuerpo = [
            {
                "to": m.token,
                "title": m.titulo,
                "body": m.cuerpo,
                "data": m.datos,
                "sound": "default",
                "priority": "high",
                "channelId": "reclamos",  # canal de Android que crea la app
            }
            for m in lote
        ]
        try:
            respuesta = self.cliente.post(self.url, json=cuerpo, headers=encabezados)
            respuesta.raise_for_status()
            tickets: list[dict[str, Any]] = respuesta.json()["data"]
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise ErrorEnvio(f"Expo Push no respondió bien: {error}") from error

        resultados = []
        for mensaje, ticket in zip(lote, tickets, strict=False):
            if ticket.get("status") == "ok":
                resultados.append(ResultadoPush(mensaje.token, ok=True))
            else:
                detalles = ticket.get("details") or {}
                resultados.append(
                    ResultadoPush(
                        mensaje.token,
                        ok=False,
                        error=detalles.get("error", "error"),
                        mensaje=str(ticket.get("message", "")),
                    )
                )
        return resultados


def get_notificador_push() -> NotificadorPush:
    settings = get_settings()
    if settings.push_modo is PushModo.EXPO:
        return PushExpo(settings.expo_push_url, settings.expo_access_token)
    return PushFalso()
