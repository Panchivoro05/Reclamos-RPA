"""Dependencias reutilizables de los routers."""

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import AuthMode, Settings, get_settings
from app.core.db import get_db
from app.core.errores import NoAutenticado
from app.core.security import verificar_token_firebase
from app.models import Cliente
from app.services import clientes
from app.services.almacenamiento import AlmacenamientoArchivos, get_almacenamiento

DbSession = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
Almacenamiento = Annotated[AlmacenamientoArchivos, Depends(get_almacenamiento)]


def get_cliente_actual(
    db: DbSession,
    settings: SettingsDep,
    x_dev_user: Annotated[str | None, Header(alias="X-Dev-User")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Cliente:
    """Cliente que hace la petición, según AUTH_MODE.

    - dev: el encabezado X-Dev-User trae el correo del cliente (solo desarrollo y pruebas).
    - firebase: Authorization: Bearer <ID token de Firebase>.
    """
    if settings.auth_mode is AuthMode.DEV:
        if not x_dev_user:
            raise NoAutenticado(
                "sin_sesion", "Falta el encabezado X-Dev-User con el correo del cliente."
            )
        cliente = clientes.obtener_por_email(db, x_dev_user)
        if cliente is None:
            raise NoAutenticado("sin_sesion", f"No existe un cliente con el correo {x_dev_user}.")
        return cliente

    esquema, _, token = (authorization or "").partition(" ")
    if esquema.lower() != "bearer" or not token:
        raise NoAutenticado("sin_sesion", "Inicia sesión para continuar.")
    return clientes.obtener_o_crear_desde_firebase(db, verificar_token_firebase(token))


ClienteActual = Annotated[Cliente, Depends(get_cliente_actual)]
