"""Acceso a SQLite: una conexión por petición, guardada en `flask.g`."""

import sqlite3
from importlib import resources
from pathlib import Path

from flask import Flask, current_app, g


def conectar(ruta: Path) -> sqlite3.Connection:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(ruta)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


def obtener_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = conectar(current_app.config["DB_PATH"])
    return g.db


def cerrar_db(_error: BaseException | None = None) -> None:
    conexion: sqlite3.Connection | None = g.pop("db", None)
    if conexion is not None:
        conexion.close()


def crear_esquema(conexion: sqlite3.Connection) -> None:
    esquema = resources.files("caja").joinpath("schema.sql").read_text(encoding="utf-8")
    conexion.executescript(esquema)


def registrar(app: Flask) -> None:
    app.teardown_appcontext(cerrar_db)
