import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from caja import create_app, db
from caja.operadores import guardar_operador

USUARIO = "cajero_prueba"
CLAVE = "clave-de-prueba"


@pytest.fixture
def app(tmp_path: Path) -> Iterator[Flask]:
    """App con una base SQLite nueva en una carpeta temporal para cada prueba."""
    ruta = tmp_path / "caja.db"
    conexion = db.conectar(ruta)
    db.crear_esquema(conexion)
    guardar_operador(conexion, USUARIO, "Cajero de Prueba", CLAVE)
    insertar_pedido(conexion)
    conexion.close()
    yield create_app({"TESTING": True, "DB_PATH": ruta, "SECRET_KEY": "pruebas"})


@pytest.fixture
def cliente(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def con_sesion(cliente: FlaskClient) -> FlaskClient:
    respuesta = iniciar_sesion(cliente, USUARIO, CLAVE)
    assert respuesta.status_code == 302
    return cliente


def token_csrf(cliente: FlaskClient, ruta: str = "/login") -> str:
    html = cliente.get(ruta).get_data(as_text=True)
    encontrado = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert encontrado, "la página no tiene token CSRF"
    return encontrado.group(1)


def iniciar_sesion(cliente: FlaskClient, usuario: str, clave: str, **extra: str) -> TestResponse:
    datos = {"usuario": usuario, "clave": clave, "csrf_token": token_csrf(cliente), **extra}
    return cliente.post("/login", data=datos)


def insertar_pedido(conexion: sqlite3.Connection) -> None:
    """Pedido BY-000101: 2 Clásica (S/ 18.90) + 1 Papas (S/ 8.50) = S/ 46.30."""
    cursor = conexion.execute(
        """
        INSERT INTO pedidos (codigo, cliente_nombre, cliente_email, estado, total_centimos,
                             local, direccion_entrega, creado_en, entregado_en, sincronizado_en)
        VALUES ('BY-000101', 'María Quispe', 'cliente1@burgerya.pe', 'entregado', 4630,
                'BurgerYa Miraflores', 'Av. Larco 123', '2026-10-27T17:00:00+00:00',
                '2026-10-27T17:45:00+00:00', '2026-10-27T18:00:00+00:00')
        """
    )
    conexion.executemany(
        "INSERT INTO pedido_items (pedido_id, producto, cantidad, precio_unitario_centimos) "
        "VALUES (?, ?, ?, ?)",
        [(cursor.lastrowid, "Hamburguesa Clásica", 2, 1890), (cursor.lastrowid, "Papas", 1, 850)],
    )
    conexion.commit()
