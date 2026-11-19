from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Cliente, EstadoPedido, Pedido, PedidoItem, Producto, Reclamo
from app.seed import reiniciar_reclamos, seed
from tests.utils import crear_reclamo


def _contar(db: Session, modelo: type) -> int:
    return db.scalar(select(func.count()).select_from(modelo)) or 0


def test_seed_es_idempotente(db: Session) -> None:
    seed(db)
    seed(db)

    assert _contar(db, Producto) == 14
    assert _contar(db, Cliente) == 2
    assert _contar(db, Pedido) == 8
    assert _contar(db, PedidoItem) == 22


def test_total_de_cada_pedido_coincide_con_sus_items(db: Session, datos: None) -> None:
    for pedido in db.scalars(select(Pedido)):
        esperado = sum((i.precio_unitario * i.cantidad for i in pedido.items), Decimal("0"))
        assert pedido.total == esperado, pedido.codigo


def test_seed_recalcula_fechas_respecto_de_ahora(db: Session) -> None:
    ahora = datetime(2026, 10, 26, 18, 0, tzinfo=UTC)
    seed(db, ahora=ahora)
    seed(db, ahora=ahora + timedelta(days=1))

    pedido = db.scalars(select(Pedido).where(Pedido.codigo == "BY-000101")).one()
    assert pedido.estado is EstadoPedido.ENTREGADO
    assert pedido.entregado_en == ahora + timedelta(days=1) - timedelta(minutes=30)


def test_reiniciar_reclamos_borra_reclamos_y_evidencia(
    client: TestClient, db: Session, datos: None, tmp_path: Path
) -> None:
    assert crear_reclamo(client).status_code == 201
    evidencia = tmp_path / "evidencias" / "RC-2026-000001" / "intento-1"
    evidencia.mkdir(parents=True)
    (evidencia / "video.webm").write_bytes(b"x")

    assert reiniciar_reclamos(db, tmp_path) == 1
    assert db.scalar(select(func.count(Reclamo.id))) == 0
    assert not (tmp_path / "evidencias").exists()
    # Los pedidos siguen y el correlativo no se repite (SISCAJA guarda los códigos viejos).
    assert db.scalar(select(func.count(Pedido.id))) == 8
    nuevo = crear_reclamo(client)
    assert nuevo.json()["codigo"].endswith("-000002")
