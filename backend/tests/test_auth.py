from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import deps
from app.core.errores import NoAutenticado
from app.core.security import IdentidadFirebase
from app.models import Cliente
from tests.utils import CLIENTE1


def test_health(client: TestClient) -> None:
    respuesta = client.get("/api/v1/health")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}


def test_me_devuelve_el_cliente_actual(client: TestClient, datos: None) -> None:
    respuesta = client.get("/api/v1/me", headers=CLIENTE1)
    assert respuesta.status_code == 200
    assert respuesta.json()["email"] == "cliente1@burgerya.pe"
    assert respuesta.json()["nombre"] == "María Quispe"


def test_dev_acepta_correo_con_mayusculas(client: TestClient, datos: None) -> None:
    respuesta = client.get("/api/v1/me", headers={"X-Dev-User": " Cliente1@BurgerYa.pe "})
    assert respuesta.status_code == 200


def test_sin_encabezado_responde_401(client: TestClient, datos: None) -> None:
    respuesta = client.get("/api/v1/me")
    assert respuesta.status_code == 401
    assert respuesta.json()["codigo"] == "sin_sesion"


def test_correo_desconocido_responde_401(client: TestClient, datos: None) -> None:
    respuesta = client.get("/api/v1/me", headers={"X-Dev-User": "nadie@burgerya.pe"})
    assert respuesta.status_code == 401


# ---------- Modo firebase (el token se simula: no se llama a Google) ----------


@pytest.fixture
def modo_firebase(
    configurar: Callable[..., None], monkeypatch: pytest.MonkeyPatch
) -> Callable[[IdentidadFirebase], None]:
    configurar(auth_mode="firebase")

    def _token_valido_para(identidad: IdentidadFirebase) -> None:
        def verificar(token: str) -> IdentidadFirebase:
            if token != "token-valido":
                raise NoAutenticado("token_invalido", "Token inválido.")
            return identidad

        monkeypatch.setattr(deps, "verificar_token_firebase", verificar)

    return _token_valido_para


BEARER = {"Authorization": "Bearer token-valido"}


def test_firebase_crea_cliente_nuevo(
    client: TestClient, db: Session, modo_firebase: Callable[[IdentidadFirebase], None]
) -> None:
    modo_firebase(IdentidadFirebase(uid="uid-nuevo", email="Nueva@Correo.pe", nombre="Ana Torres"))

    respuesta = client.get("/api/v1/me", headers=BEARER)

    assert respuesta.status_code == 200
    cliente = db.scalars(select(Cliente).where(Cliente.firebase_uid == "uid-nuevo")).one()
    assert cliente.email == "nueva@correo.pe"
    assert cliente.nombre == "Ana Torres"


def test_firebase_vincula_cliente_existente_por_correo(
    client: TestClient,
    db: Session,
    datos: None,
    modo_firebase: Callable[[IdentidadFirebase], None],
) -> None:
    modo_firebase(IdentidadFirebase(uid="uid-1", email="cliente1@burgerya.pe", nombre=None))

    assert client.get("/api/v1/me", headers=BEARER).json()["nombre"] == "María Quispe"
    # La segunda vez lo encuentra por su uid.
    assert client.get("/api/v1/me", headers=BEARER).status_code == 200
    clientes = db.scalars(select(Cliente).where(Cliente.firebase_uid == "uid-1")).all()
    assert len(clientes) == 1


def test_firebase_ignora_x_dev_user(
    client: TestClient, datos: None, modo_firebase: Callable[[IdentidadFirebase], None]
) -> None:
    modo_firebase(IdentidadFirebase(uid="uid-1", email="cliente1@burgerya.pe", nombre=None))
    assert client.get("/api/v1/me", headers=CLIENTE1).status_code == 401


def test_firebase_token_invalido_responde_401(
    client: TestClient, modo_firebase: Callable[[IdentidadFirebase], None]
) -> None:
    modo_firebase(IdentidadFirebase(uid="uid-1", email="a@b.pe", nombre=None))
    respuesta = client.get("/api/v1/me", headers={"Authorization": "Bearer otro"})
    assert respuesta.status_code == 401
    assert respuesta.headers["WWW-Authenticate"] == "Bearer"
