"""Registro y baja de los tokens de Expo Push."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Dispositivo
from tests.utils import CLIENTE1, CLIENTE2

TOKEN = "ExponentPushToken[abc123XYZ]"


def registrar(client: TestClient, headers: dict[str, str] = CLIENTE1, **datos: str) -> int:
    cuerpo = {"token": TOKEN, "plataforma": "android", **datos}
    return client.post("/api/v1/dispositivos", json=cuerpo, headers=headers).status_code


def dispositivos(db: Session) -> list[tuple[str, int, bool]]:
    db.expire_all()
    return [
        (d.token, d.cliente_id, d.activo)
        for d in db.scalars(select(Dispositivo).order_by(Dispositivo.id))
    ]


def test_registrar_es_idempotente(client: TestClient, db: Session, datos: None) -> None:
    assert registrar(client) == 204
    assert registrar(client) == 204
    assert len(dispositivos(db)) == 1
    assert dispositivos(db)[0][2] is True


def test_el_celular_pasa_al_ultimo_cliente_que_inicia_sesion(
    client: TestClient, db: Session, datos: None
) -> None:
    registrar(client, CLIENTE1)
    registrar(client, CLIENTE2)
    (_, cliente_id, _), *otros = dispositivos(db)
    assert otros == []
    assert cliente_id == client.get("/api/v1/me", headers=CLIENTE2).json()["id"]


def test_al_cerrar_sesion_se_da_de_baja(client: TestClient, db: Session, datos: None) -> None:
    registrar(client)
    respuesta = client.delete(f"/api/v1/dispositivos/{TOKEN}", headers=CLIENTE1)
    assert respuesta.status_code == 204
    assert dispositivos(db)[0][2] is False
    # Al volver a iniciar sesión se reactiva.
    registrar(client)
    assert dispositivos(db)[0][2] is True


def test_otro_cliente_no_puede_dar_de_baja_mi_celular(
    client: TestClient, db: Session, datos: None
) -> None:
    registrar(client, CLIENTE1)
    assert client.delete(f"/api/v1/dispositivos/{TOKEN}", headers=CLIENTE2).status_code == 204
    assert dispositivos(db)[0][2] is True


def test_token_con_formato_invalido(client: TestClient, datos: None) -> None:
    assert registrar(client, token="no-es-un-token") == 422
    assert registrar(client, plataforma="windows") == 422


def test_requiere_sesion(client: TestClient, datos: None) -> None:
    respuesta = client.post("/api/v1/dispositivos", json={"token": TOKEN, "plataforma": "ios"})
    assert respuesta.status_code == 401
