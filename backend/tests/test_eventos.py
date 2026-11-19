"""Cada cambio de estado se publica en tiempo real, después de guardarse."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Cliente, EstadoReclamo, Reclamo
from app.services import eventos
from app.services.bot import EjecutorBotSimulado
from tests.test_procesamiento import nuevo_reclamo, procesar, un_combo

Publicados = list[tuple[str, dict[str, object]]]


def id_cliente(email: str) -> int:
    with SessionLocal() as session:
        return session.scalars(select(Cliente.id).where(Cliente.email == email)).one()


def estados(publicados: Publicados) -> list[object]:
    return [mensaje["estado"] for _, mensaje in publicados]


def test_crear_reclamo_publica_recibido_en_el_canal_del_cliente(
    client: TestClient, datos: None, publicados: Publicados
) -> None:
    nuevo_reclamo(client, items=un_combo(client))

    assert len(publicados) == 1
    canal, mensaje = publicados[0]
    assert canal == f"reclamos:cliente:{id_cliente('cliente1@burgerya.pe')}"
    assert mensaje["tipo"] == "reclamo_actualizado"
    assert mensaje["codigo"] == "RC-2026-000001"
    assert mensaje["estado"] == "recibido"
    assert isinstance(mensaje["evento_id"], int)
    assert "T" in str(mensaje["momento"])


def test_el_procesamiento_publica_cada_paso_en_orden(
    client: TestClient, datos: None, publicados: Publicados
) -> None:
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))
    procesar(reclamo_id, EjecutorBotSimulado())

    assert estados(publicados) == [
        "recibido",
        "en_validacion",
        "validado",
        "en_resolucion",
        "resuelto",
    ]
    evento_ids = [mensaje["evento_id"] for _, mensaje in publicados]
    assert evento_ids == sorted(evento_ids) and len(set(evento_ids)) == 5


def test_escalado_tambien_se_publica(
    client: TestClient, datos: None, publicados: Publicados
) -> None:
    reclamo_id = nuevo_reclamo(client, items=un_combo(client, cantidad=2))  # S/ 55.80 > S/ 40
    procesar(reclamo_id, EjecutorBotSimulado())
    assert estados(publicados) == ["recibido", "en_validacion", "escalado"]


def test_se_publica_despues_del_commit(
    client: TestClient, datos: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Al publicar, otra conexión ya ve el estado nuevo (la app no lee un estado viejo)."""
    vistos: list[tuple[str, EstadoReclamo]] = []

    def _publicar(canal: str, mensaje: str) -> None:
        datos = json.loads(mensaje)
        with SessionLocal() as otra:
            estado = otra.scalars(
                select(Reclamo.estado).where(Reclamo.codigo == datos["codigo"])
            ).one()
        vistos.append((datos["estado"], estado))

    monkeypatch.setattr(eventos, "_publicar", _publicar)
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))
    procesar(reclamo_id, EjecutorBotSimulado())

    assert vistos and all(publicado == guardado.value for publicado, guardado in vistos)


def test_valkey_caido_no_impide_registrar_ni_procesar(
    client: TestClient, datos: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _caido(canal: str, mensaje: str) -> None:
        raise ConnectionError("Valkey no responde")

    monkeypatch.setattr(eventos, "_publicar", _caido)
    reclamo_id = nuevo_reclamo(client, items=un_combo(client))
    procesar(reclamo_id, EjecutorBotSimulado())

    with SessionLocal() as session:
        reclamo = session.get(Reclamo, reclamo_id)
        assert reclamo is not None and reclamo.estado == EstadoReclamo.RESUELTO
