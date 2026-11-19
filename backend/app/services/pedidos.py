from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import NoEncontrado
from app.models import Cliente, Pedido, Reclamo, ReclamoItem


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


def unidades_reclamadas(session: Session, pedido: Pedido) -> dict[int, int]:
    """Unidades de cada producto del pedido que ya están en algún reclamo (de cualquier tipo
    y estado): {pedido_item_id: unidades}. Una unidad solo se compensa una vez."""
    filas = session.execute(
        select(ReclamoItem.pedido_item_id, func.sum(ReclamoItem.cantidad_afectada))
        .join(Reclamo, Reclamo.id == ReclamoItem.reclamo_id)
        .where(Reclamo.pedido_id == pedido.id)
        .group_by(ReclamoItem.pedido_item_id)
    )
    return {item_id: int(unidades) for item_id, unidades in filas}
