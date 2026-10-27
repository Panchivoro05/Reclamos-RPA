"""Verificación de identidad con Firebase Authentication.

Solo se usa con AUTH_MODE=firebase. La app inicia sesión con Firebase y envía el
ID token en el encabezado Authorization: Bearer <token>; aquí se valida su firma.
"""

from dataclasses import dataclass
from functools import lru_cache

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from firebase_admin import exceptions as firebase_exceptions

from app.core.config import get_settings
from app.core.errores import NoAutenticado


@dataclass(frozen=True)
class IdentidadFirebase:
    uid: str
    email: str | None
    nombre: str | None


@lru_cache
def _firebase_app() -> firebase_admin.App:
    ruta = get_settings().firebase_credentials_path
    credencial = credentials.Certificate(ruta) if ruta else credentials.ApplicationDefault()
    return firebase_admin.initialize_app(credencial)


def verificar_token_firebase(token: str) -> IdentidadFirebase:
    try:
        claims = firebase_auth.verify_id_token(token, app=_firebase_app())
    except (ValueError, firebase_exceptions.FirebaseError) as error:
        raise NoAutenticado(
            "token_invalido", "Tu sesión expiró o no es válida. Vuelve a iniciar sesión."
        ) from error

    email = claims.get("email")
    nombre = claims.get("name")
    return IdentidadFirebase(
        uid=str(claims["uid"]),
        email=str(email) if email else None,
        nombre=str(nombre) if nombre else None,
    )
