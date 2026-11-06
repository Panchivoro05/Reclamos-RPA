"""Operadores de caja: alta y verificación de credenciales."""

import sqlite3
from dataclasses import dataclass

from werkzeug.security import check_password_hash, generate_password_hash

from caja.db import obtener_db
from caja.formato import ahora_utc_iso


@dataclass(frozen=True)
class Operador:
    id: int
    usuario: str
    nombre: str


def guardar_operador(conexion: sqlite3.Connection, usuario: str, nombre: str, clave: str) -> None:
    """Crea el operador o actualiza su nombre y clave si ya existe."""
    conexion.execute(
        """
        INSERT INTO operadores (usuario, nombre, clave_hash, activo, creado_en)
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT (usuario) DO UPDATE
        SET nombre = excluded.nombre, clave_hash = excluded.clave_hash, activo = 1
        """,
        (usuario, nombre, generate_password_hash(clave), ahora_utc_iso()),
    )
    conexion.commit()


def autenticar(usuario: str, clave: str) -> Operador | None:
    fila = (
        obtener_db()
        .execute(
            "SELECT id, usuario, nombre, clave_hash FROM operadores "
            "WHERE usuario = ? AND activo = 1",
            (usuario.strip(),),
        )
        .fetchone()
    )
    if fila is None or not check_password_hash(fila["clave_hash"], clave):
        return None
    return Operador(fila["id"], fila["usuario"], fila["nombre"])


def obtener_operador(operador_id: int) -> Operador | None:
    fila = (
        obtener_db()
        .execute(
            "SELECT id, usuario, nombre FROM operadores WHERE id = ? AND activo = 1",
            (operador_id,),
        )
        .fetchone()
    )
    return Operador(fila["id"], fila["usuario"], fila["nombre"]) if fila else None
