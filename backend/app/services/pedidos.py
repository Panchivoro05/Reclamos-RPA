from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import NoEncontrado
from app.models import Cliente, Pedido


def listar_pedidos(session: Session, cliente: Cliente) -> Sequence[Pedido]:
    return session.scalars(
        select(Pedido)
        .where(Pedido.cliente_id == cliente.id)
        .options(selectinload(Pedido.items))
        .order_by(Pedido.creado_en.desc(), Pedido.id.desc())
    ).all()


def obtener_pedido(session: Session, cliente: Cliente, codigo: str) -> Pedido:
    """Pedido del cliente actual. Un pedido ajeno responde igual que uno inexistente (404)."""
    codigo = codigo.strip().upper()
    pedido = session.scalar(
        select(Pedido)
        .where(Pedido.codigo == codigo, Pedido.cliente_id == cliente.id)
        .options(selectinload(Pedido.items))
    )
    if pedido is None:
        raise NoEncontrado(
            "pedido_no_encontrado", f"No encontramos el pedido {codigo} en tu cuenta."
        )
    return pedido
