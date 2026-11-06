"""Sincronización desde una base de ventas de prueba en PostgreSQL (siscaja_test).

Las tablas de ventas se crean aquí con solo las columnas que lee la sincronización. En CI,
además, se sincroniza contra la base real del backend (migrada y con datos de prueba), para
detectar si cambian sus columnas.
"""

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from flask import Flask

from caja import db
from caja.sincronizacion import sincronizar, url_psycopg

URL_PRUEBA = os.environ.get(
    "CAJA_TEST_VENTAS_DATABASE_URL",
    "postgresql://reclamos:reclamos_dev@127.0.0.1:5432/siscaja_test",
)

ESQUEMA_VENTAS = """
    DROP TABLE IF EXISTS pedido_items, pedidos, productos, clientes CASCADE;
    DROP TYPE IF EXISTS estado_pedido;
    CREATE TYPE estado_pedido AS ENUM ('en_preparacion', 'en_camino', 'entregado', 'cancelado');
    CREATE TABLE clientes (id serial PRIMARY KEY, email text NOT NULL, nombre text NOT NULL);
    CREATE TABLE productos (id serial PRIMARY KEY, nombre text NOT NULL);
    CREATE TABLE pedidos (
        id serial PRIMARY KEY, codigo text NOT NULL UNIQUE, cliente_id int REFERENCES clientes,
        estado estado_pedido NOT NULL, total numeric(10, 2) NOT NULL, direccion_entrega text,
        local text, creado_en timestamptz NOT NULL, entregado_en timestamptz
    );
    CREATE TABLE pedido_items (
        id serial PRIMARY KEY, pedido_id int REFERENCES pedidos ON DELETE CASCADE,
        producto_id int REFERENCES productos, cantidad int NOT NULL,
        precio_unitario numeric(10, 2) NOT NULL
    );
    INSERT INTO clientes (email, nombre) VALUES ('cliente1@burgerya.pe', 'María Quispe');
    INSERT INTO productos (nombre) VALUES ('Hamburguesa Clásica'), ('Papas'), ('Inca Kola');
    INSERT INTO pedidos (codigo, cliente_id, estado, total, direccion_entrega, local,
                         creado_en, entregado_en)
    VALUES ('BY-000201', 1, 'entregado', 46.30, 'Av. Larco 123', 'BurgerYa Miraflores',
            '2026-10-27 17:00+00', '2026-10-27 17:45+00'),
           ('BY-000202', 1, 'en_camino', 6.50, 'Av. Larco 123', 'BurgerYa Miraflores',
            '2026-10-27 18:00+00', NULL);
    INSERT INTO pedido_items (pedido_id, producto_id, cantidad, precio_unitario)
    VALUES (1, 1, 2, 18.90), (1, 2, 1, 8.50), (2, 3, 1, 6.50);
"""


def _crear_base_si_falta() -> None:
    nombre = psycopg.conninfo.conninfo_to_dict(URL_PRUEBA)["dbname"]
    mantenimiento = psycopg.conninfo.make_conninfo(URL_PRUEBA, dbname="postgres")
    with psycopg.connect(mantenimiento, autocommit=True) as conexion:
        existe = conexion.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nombre,))
        if existe.fetchone() is None:
            conexion.execute(f'CREATE DATABASE "{nombre}"')


@pytest.fixture
def ventas() -> Iterator[psycopg.Connection]:
    try:
        _crear_base_si_falta()
    except psycopg.OperationalError as e:
        pytest.fail(f"PostgreSQL no está disponible ({e}). Levanta infra/compose.yml.")
    with psycopg.connect(URL_PRUEBA, autocommit=True) as conexion:
        conexion.execute(ESQUEMA_VENTAS)
        yield conexion


@pytest.fixture
def caja_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    conexion = db.conectar(tmp_path / "caja.db")
    db.crear_esquema(conexion)
    yield conexion
    conexion.close()


def test_copia_pedidos_e_items(ventas: psycopg.Connection, caja_db: sqlite3.Connection) -> None:
    resumen = sincronizar(caja_db, URL_PRUEBA)
    assert (resumen.nuevos, resumen.actualizados) == (2, 0)

    pedido = caja_db.execute("SELECT * FROM pedidos WHERE codigo = 'BY-000201'").fetchone()
    assert pedido["cliente_nombre"] == "María Quispe"
    assert pedido["cliente_email"] == "cliente1@burgerya.pe"
    assert pedido["estado"] == "entregado"
    assert pedido["total_centimos"] == 4630
    assert pedido["entregado_en"] == "2026-10-27T17:45:00+00:00"
    items = caja_db.execute(
        "SELECT producto, cantidad, precio_unitario_centimos FROM pedido_items "
        "WHERE pedido_id = ? ORDER BY id",
        (pedido["id"],),
    ).fetchall()
    assert [tuple(i) for i in items] == [("Hamburguesa Clásica", 2, 1890), ("Papas", 1, 850)]

    en_camino = caja_db.execute("SELECT * FROM pedidos WHERE codigo = 'BY-000202'").fetchone()
    assert en_camino["entregado_en"] is None


def test_repetir_actualiza_sin_duplicar(
    ventas: psycopg.Connection, caja_db: sqlite3.Connection
) -> None:
    sincronizar(caja_db, URL_PRUEBA)
    ventas.execute(
        "UPDATE pedidos SET estado = 'entregado', entregado_en = '2026-10-27 18:30+00' "
        "WHERE codigo = 'BY-000202'"
    )
    ventas.execute("UPDATE pedido_items SET cantidad = 2 WHERE pedido_id = 2")

    resumen = sincronizar(caja_db, URL_PRUEBA)
    assert (resumen.nuevos, resumen.actualizados) == (0, 2)
    assert caja_db.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0] == 2
    assert caja_db.execute("SELECT COUNT(*) FROM pedido_items").fetchone()[0] == 3

    pedido = caja_db.execute("SELECT * FROM pedidos WHERE codigo = 'BY-000202'").fetchone()
    assert pedido["estado"] == "entregado"
    cantidad = caja_db.execute(
        "SELECT cantidad FROM pedido_items WHERE pedido_id = ?", (pedido["id"],)
    ).fetchone()[0]
    assert cantidad == 2


def test_conserva_compensaciones_y_pedidos_que_ya_no_estan_en_ventas(
    ventas: psycopg.Connection, caja_db: sqlite3.Connection
) -> None:
    sincronizar(caja_db, URL_PRUEBA)
    caja_db.execute(
        "INSERT INTO operadores (usuario, nombre, clave_hash, creado_en) "
        "VALUES ('cajero', 'Cajero', 'x', '2026-10-27T00:00:00+00:00')"
    )
    caja_db.execute(
        "INSERT INTO compensaciones (numero, pedido_id, tipo, monto_centimos, motivo, "
        "operador_id, creado_en) SELECT 'CMP-000001', id, 'cupon', 500, 'Motivo de prueba', 1, "
        "'2026-10-27T19:00:00+00:00' FROM pedidos WHERE codigo = 'BY-000201'"
    )
    caja_db.commit()
    ventas.execute("DELETE FROM pedidos WHERE codigo = 'BY-000201'")

    resumen = sincronizar(caja_db, URL_PRUEBA)
    assert resumen.total == 1
    assert caja_db.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0] == 2
    assert caja_db.execute("SELECT COUNT(*) FROM compensaciones").fetchone()[0] == 1


def test_comando_flask_sincronizar(ventas: psycopg.Connection, app: Flask) -> None:
    app.config["VENTAS_DATABASE_URL"] = URL_PRUEBA
    resultado = app.test_cli_runner().invoke(args=["sincronizar"])
    assert resultado.exit_code == 0, resultado.output
    # El pedido BY-000101 del conftest ya existía; los dos de ventas son nuevos.
    assert "2 pedidos nuevos, 0 actualizados" in resultado.output


def test_comando_informa_si_no_hay_conexion(app: Flask) -> None:
    app.config["VENTAS_DATABASE_URL"] = "postgresql://nadie:x@127.0.0.1:1/ventas?connect_timeout=2"
    resultado = app.test_cli_runner().invoke(args=["sincronizar"])
    assert resultado.exit_code != 0
    assert "No se pudo conectar con la base de ventas" in resultado.output


def test_acepta_la_url_de_sqlalchemy_del_backend() -> None:
    assert url_psycopg("postgresql+psycopg://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"
    assert url_psycopg("postgresql://u:p@h/db") == "postgresql://u:p@h/db"
