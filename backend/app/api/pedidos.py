from fastapi import APIRouter

from app.api.deps import ClienteActual, DbSession
from app.schemas.pedido import PedidoDetalle, PedidoResumen
from app.services import pedidos, reclamos

router = APIRouter(prefix="/pedidos", tags=["pedidos"])


@router.get("")
def listar_pedidos(db: DbSession, cliente: ClienteActual) -> list[PedidoResumen]:
    return [PedidoResumen.desde(p) for p in pedidos.listar_pedidos(db, cliente)]


@router.get("/{codigo}")
def obtener_pedido(db: DbSession, cliente: ClienteActual, codigo: str) -> PedidoDetalle:
    pedido = pedidos.obtener_pedido(db, cliente, codigo)
    return PedidoDetalle.desde_pedido(pedido, reclamos.tipos_disponibles(db, pedido))
