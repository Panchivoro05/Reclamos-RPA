"""Consulta de pedidos copiados del sistema de ventas."""

import sqlite3
from dataclasses import dataclass

from caja.db import obtener_db

ESTADOS = {
    "en_preparacion": "EN PREPARACION",
    "en_camino": "EN CAMINO",
    "entregado": "ENTREGADO",
    "cancelado": "CANCELADO",
}


@dataclass(frozen=True)
class ItemPedido:
    producto: str
    cantidad: int
    precio_unitario_centimos: int

    @property
    def subtotal_centimos(self) -> int:
        return self.cantidad * self.precio_unitario_centimos


@dataclass(frozen=True)
class Pedido:
    id: int
    codigo: str
    cliente_nombre: str
    cliente_email: str
    estado: str
    total_centimos: int
    local: str
    direccion_entrega: str
    creado_en: str
    entregado_en: str | None
    sincronizado_en: str
    items: list[ItemPedido]

    @property
    def estado_texto(self) -> str:
        return ESTADOS.get(self.estado, self.estado.upper())


def normalizar_codigo(codigo: str) -> str:
    return codigo.strip().upper()


def buscar_pedido(codigo: str) -> Pedido | None:
    conexion = obtener_db()
    fila = conexion.execute(
        "SELECT * FROM pedidos WHERE codigo = ?", (normalizar_codigo(codigo),)
    ).fetchone()
    return _armar_pedido(conexion, fila) if fila else None


def _armar_pedido(conexion: sqlite3.Connection, fila: sqlite3.Row) -> Pedido:
    items = [
        ItemPedido(i["producto"], i["cantidad"], i["precio_unitario_centimos"])
        for i in conexion.execute(
            "SELECT producto, cantidad, precio_unitario_centimos FROM pedido_items "
            "WHERE pedido_id = ? ORDER BY id",
            (fila["id"],),
        )
    ]
    return Pedido(
        id=fila["id"],
        codigo=fila["codigo"],
        cliente_nombre=fila["cliente_nombre"],
        cliente_email=fila["cliente_email"],
        estado=fila["estado"],
        total_centimos=fila["total_centimos"],
        local=fila["local"],
        direccion_entrega=fila["direccion_entrega"],
        creado_en=fila["creado_en"],
        entregado_en=fila["entregado_en"],
        sincronizado_en=fila["sincronizado_en"],
        items=items,
    )
