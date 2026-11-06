"""Sincronización por lotes: copia los pedidos del sistema de ventas (PostgreSQL) a SISCAJA.

Simula que ventas y caja comparten los datos de ventas, como ocurre en muchas empresas con
procesos nocturnos. No es una API: SISCAJA sigue sin exponer nada; solo LEE la base de ventas.
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

from caja.formato import ahora_utc_iso

CONSULTA_PEDIDOS = """
    SELECT p.id, p.codigo, c.nombre AS cliente_nombre, c.email AS cliente_email,
           p.estado::text AS estado, p.total, p.local, p.direccion_entrega,
           p.creado_en, p.entregado_en
    FROM pedidos p
    JOIN clientes c ON c.id = p.cliente_id
    ORDER BY p.codigo
"""

CONSULTA_ITEMS = """
    SELECT pi.pedido_id, pr.nombre AS producto, pi.cantidad, pi.precio_unitario
    FROM pedido_items pi
    JOIN productos pr ON pr.id = pi.producto_id
    ORDER BY pi.pedido_id, pi.id
"""


@dataclass(frozen=True)
class ItemVentas:
    producto: str
    cantidad: int
    precio_unitario: Decimal


@dataclass
class PedidoVentas:
    id: int
    codigo: str
    cliente_nombre: str
    cliente_email: str
    estado: str
    total: Decimal
    local: str
    direccion_entrega: str
    creado_en: datetime
    entregado_en: datetime | None
    items: list[ItemVentas] = field(default_factory=list)


@dataclass(frozen=True)
class ResumenSincronizacion:
    nuevos: int
    actualizados: int

    @property
    def total(self) -> int:
        return self.nuevos + self.actualizados


def url_psycopg(url: str) -> str:
    """Acepta la URL de SQLAlchemy del backend (postgresql+psycopg://) y la deja para psycopg."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def a_centimos(monto: Decimal) -> int:
    return int((monto * 100).to_integral_value())


def a_iso(fecha: datetime | None) -> str | None:
    return fecha.isoformat(timespec="seconds") if fecha else None


def leer_ventas(url: str) -> list[PedidoVentas]:
    """Lee pedidos e ítems de ventas en una transacción de SOLO LECTURA."""
    with psycopg.connect(url_psycopg(url), row_factory=dict_row) as conexion:
        conexion.read_only = True  # PostgreSQL rechaza cualquier escritura en esta sesión
        pedidos = {fila["id"]: PedidoVentas(**fila) for fila in conexion.execute(CONSULTA_PEDIDOS)}
        for fila in conexion.execute(CONSULTA_ITEMS):
            pedidos[fila.pop("pedido_id")].items.append(ItemVentas(**fila))
    return list(pedidos.values())


def sincronizar(destino: sqlite3.Connection, url_ventas: str) -> ResumenSincronizacion:
    """Copia o actualiza los pedidos en SISCAJA. Se puede repetir sin duplicar nada.

    Nunca borra pedidos ni compensaciones: si un pedido desaparece de ventas, su historial
    de compensaciones se conserva en caja.
    """
    pedidos = leer_ventas(url_ventas)
    ahora = ahora_utc_iso()
    nuevos = actualizados = 0

    with destino:  # una sola transacción: o se copia todo o nada
        for pedido in pedidos:
            valores = (
                pedido.cliente_nombre,
                pedido.cliente_email,
                pedido.estado,
                a_centimos(pedido.total),
                pedido.local,
                pedido.direccion_entrega,
                a_iso(pedido.creado_en),
                a_iso(pedido.entregado_en),
                ahora,
            )
            fila = destino.execute(
                "SELECT id FROM pedidos WHERE codigo = ?", (pedido.codigo,)
            ).fetchone()
            if fila is None:
                cursor = destino.execute(
                    """
                    INSERT INTO pedidos (cliente_nombre, cliente_email, estado, total_centimos,
                        local, direccion_entrega, creado_en, entregado_en, sincronizado_en, codigo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (*valores, pedido.codigo),
                )
                pedido_id = cursor.lastrowid
                nuevos += 1
            else:
                pedido_id = fila[0]
                destino.execute(
                    """
                    UPDATE pedidos SET cliente_nombre = ?, cliente_email = ?, estado = ?,
                        total_centimos = ?, local = ?, direccion_entrega = ?, creado_en = ?,
                        entregado_en = ?, sincronizado_en = ?
                    WHERE id = ?
                    """,
                    (*valores, pedido_id),
                )
                actualizados += 1

            # Los ítems se reemplazan completos: las compensaciones apuntan al pedido, no al ítem.
            destino.execute("DELETE FROM pedido_items WHERE pedido_id = ?", (pedido_id,))
            destino.executemany(
                "INSERT INTO pedido_items (pedido_id, producto, cantidad, precio_unitario_centimos)"
                " VALUES (?, ?, ?, ?)",
                [
                    (pedido_id, item.producto, item.cantidad, a_centimos(item.precio_unitario))
                    for item in pedido.items
                ],
            )

    return ResumenSincronizacion(nuevos=nuevos, actualizados=actualizados)
