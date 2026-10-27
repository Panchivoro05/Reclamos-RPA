"""Datos de prueba de BurgerYa.

Uso: python -m app.seed

Es idempotente: se puede ejecutar varias veces sin duplicar nada. Cada ejecución
recalcula las fechas de los pedidos demo respecto de la hora actual, así el pedido
"entregado hace 30 minutos" sigue dentro del plazo de reclamo el día de la demo.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import CategoriaProducto, Cliente, EstadoPedido, Pedido, PedidoItem, Producto

logger = logging.getLogger(__name__)

MENU: list[tuple[str, CategoriaProducto, str]] = [
    ("Hamburguesa Clásica BurgerYa", CategoriaProducto.HAMBURGUESA, "18.90"),
    ("Hamburguesa Doble Queso", CategoriaProducto.HAMBURGUESA, "24.90"),
    ("Hamburguesa Royal con Huevo", CategoriaProducto.HAMBURGUESA, "22.90"),
    ("Hamburguesa BBQ con Tocino", CategoriaProducto.HAMBURGUESA, "25.90"),
    ("Hamburguesa de Pollo Crispy", CategoriaProducto.HAMBURGUESA, "19.90"),
    ("Combo Clásico (hamburguesa + papas + gaseosa)", CategoriaProducto.COMBO, "27.90"),
    ("Combo Doble Queso (hamburguesa + papas + gaseosa)", CategoriaProducto.COMBO, "34.90"),
    ("Papas Fritas Medianas", CategoriaProducto.ACOMPANAMIENTO, "8.90"),
    ("Nuggets x6", CategoriaProducto.ACOMPANAMIENTO, "12.90"),
    ("Yuquitas Fritas", CategoriaProducto.ACOMPANAMIENTO, "9.90"),
    ("Gaseosa 500 ml", CategoriaProducto.BEBIDA, "5.90"),
    ("Chicha Morada 500 ml", CategoriaProducto.BEBIDA, "6.50"),
    ("Sundae de Fudge", CategoriaProducto.POSTRE, "6.90"),
    ("Pie de Manzana", CategoriaProducto.POSTRE, "5.50"),
]

CLIENTES: list[tuple[str, str, str]] = [
    ("cliente1@burgerya.pe", "María Quispe", "+51987654321"),
    ("cliente2@burgerya.pe", "Jorge Ramírez", "+51912345678"),
]


@dataclass(frozen=True)
class PedidoDemo:
    codigo: str
    email: str
    estado: EstadoPedido
    # Minutos transcurridos desde la creación (o desde la entrega si está entregado).
    hace_minutos: int
    local: str
    direccion: str
    items: list[tuple[str, int]]


# Tiempo típico entre que se hace el pedido y se entrega.
DURACION_ENTREGA = timedelta(minutes=40)

PEDIDOS: list[PedidoDemo] = [
    PedidoDemo(
        "BY-000101",
        "cliente1@burgerya.pe",
        EstadoPedido.ENTREGADO,
        30,
        "BurgerYa Miraflores",
        "Av. José Larco 812, dpto. 501, Miraflores",
        [
            ("Combo Clásico (hamburguesa + papas + gaseosa)", 2),
            ("Nuggets x6", 1),
            ("Sundae de Fudge", 2),
        ],
    ),
    PedidoDemo(
        "BY-000102",
        "cliente1@burgerya.pe",
        EstadoPedido.EN_CAMINO,
        25,
        "BurgerYa Miraflores",
        "Av. José Larco 812, dpto. 501, Miraflores",
        [("Hamburguesa BBQ con Tocino", 1), ("Yuquitas Fritas", 1), ("Chicha Morada 500 ml", 1)],
    ),
    PedidoDemo(
        "BY-000103",
        "cliente1@burgerya.pe",
        EstadoPedido.ENTREGADO,
        3 * 24 * 60,
        "BurgerYa San Isidro",
        "Calle Las Begonias 450, oficina 302, San Isidro",
        [("Hamburguesa Doble Queso", 1), ("Papas Fritas Medianas", 1), ("Gaseosa 500 ml", 1)],
    ),
    PedidoDemo(
        "BY-000104",
        "cliente1@burgerya.pe",
        EstadoPedido.ENTREGADO,
        5 * 60,
        "BurgerYa Miraflores",
        "Av. José Larco 812, dpto. 501, Miraflores",
        [("Hamburguesa de Pollo Crispy", 2), ("Papas Fritas Medianas", 2), ("Pie de Manzana", 1)],
    ),
    PedidoDemo(
        "BY-000105",
        "cliente1@burgerya.pe",
        EstadoPedido.CANCELADO,
        10 * 24 * 60,
        "BurgerYa San Isidro",
        "Calle Las Begonias 450, oficina 302, San Isidro",
        [("Combo Doble Queso (hamburguesa + papas + gaseosa)", 1)],
    ),
    PedidoDemo(
        "BY-000106",
        "cliente2@burgerya.pe",
        EstadoPedido.ENTREGADO,
        60,
        "BurgerYa Surco",
        "Av. Primavera 1250, Santiago de Surco",
        [
            ("Hamburguesa Royal con Huevo", 1),
            ("Hamburguesa Clásica BurgerYa", 1),
            ("Papas Fritas Medianas", 2),
            ("Gaseosa 500 ml", 2),
        ],
    ),
    PedidoDemo(
        "BY-000107",
        "cliente2@burgerya.pe",
        EstadoPedido.EN_PREPARACION,
        10,
        "BurgerYa Surco",
        "Av. Primavera 1250, Santiago de Surco",
        [("Combo Doble Queso (hamburguesa + papas + gaseosa)", 1), ("Sundae de Fudge", 1)],
    ),
    PedidoDemo(
        "BY-000108",
        "cliente2@burgerya.pe",
        EstadoPedido.ENTREGADO,
        2 * 24 * 60,
        "BurgerYa Surco",
        "Av. Primavera 1250, Santiago de Surco",
        [("Nuggets x6", 2), ("Yuquitas Fritas", 1), ("Chicha Morada 500 ml", 2)],
    ),
]


def _upsert_productos(session: Session) -> dict[str, Producto]:
    existentes = {p.nombre: p for p in session.scalars(select(Producto))}
    for nombre, categoria, precio in MENU:
        producto = existentes.get(nombre)
        if producto is None:
            producto = Producto(nombre=nombre)
            session.add(producto)
            existentes[nombre] = producto
        producto.categoria = categoria
        producto.precio = Decimal(precio)
        producto.activo = True
    return existentes


def _upsert_clientes(session: Session) -> dict[str, Cliente]:
    existentes = {c.email: c for c in session.scalars(select(Cliente))}
    for email, nombre, telefono in CLIENTES:
        cliente = existentes.get(email)
        if cliente is None:
            cliente = Cliente(email=email)
            session.add(cliente)
            existentes[email] = cliente
        cliente.nombre = nombre
        cliente.telefono_whatsapp = telefono
    return existentes


def _upsert_pedidos(
    session: Session,
    productos: dict[str, Producto],
    clientes: dict[str, Cliente],
    ahora: datetime,
) -> None:
    existentes = {p.codigo: p for p in session.scalars(select(Pedido))}
    for demo in PEDIDOS:
        pedido = existentes.get(demo.codigo)
        if pedido is None:
            pedido = Pedido(codigo=demo.codigo)
            # Los ítems solo se crean la primera vez: si ya hay reclamos que apuntan
            # a ellos, recrearlos rompería esas referencias.
            pedido.items = [
                PedidoItem(
                    producto=productos[nombre],
                    cantidad=cantidad,
                    precio_unitario=productos[nombre].precio,
                )
                for nombre, cantidad in demo.items
            ]
            session.add(pedido)

        hace = ahora - timedelta(minutes=demo.hace_minutos)
        if demo.estado is EstadoPedido.ENTREGADO:
            pedido.entregado_en = hace
            pedido.creado_en = hace - DURACION_ENTREGA
        else:
            pedido.entregado_en = None
            pedido.creado_en = hace

        pedido.cliente = clientes[demo.email]
        pedido.estado = demo.estado
        pedido.local = demo.local
        pedido.direccion_entrega = demo.direccion
        pedido.total = sum(
            (item.precio_unitario * item.cantidad for item in pedido.items), Decimal("0")
        )


def seed(session: Session, ahora: datetime | None = None) -> None:
    ahora = ahora or datetime.now(UTC)
    productos = _upsert_productos(session)
    clientes = _upsert_clientes(session)
    session.flush()
    _upsert_pedidos(session, productos, clientes, ahora)
    session.commit()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with SessionLocal() as session:
        seed(session)
    logger.info(
        "Datos de prueba listos: %d productos, %d clientes, %d pedidos.",
        len(MENU),
        len(CLIENTES),
        len(PEDIDOS),
    )


if __name__ == "__main__":
    main()
