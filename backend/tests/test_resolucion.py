"""Motor de reglas y controles antifraude."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.moneda import formato_soles
from app.core.tiempo import ahora_utc
from app.models import (
    BaseMonto,
    EstadoReclamo,
    Pedido,
    PedidoItem,
    PoliticaAntifraude,
    Reclamo,
    ReclamoItem,
    ReglaResolucion,
    SolucionCompensacion,
    TipoReclamo,
)
from app.services.resolucion import (
    calcular_monto,
    contar_reclamos_en_periodo,
    decidir,
    describir_compensacion,
    evaluar_reclamo,
    reembolsado_en_pedido,
)
from tests.utils import CLIENTE2, crear_reclamo, item_id

POLITICA = PoliticaAntifraude(
    monto_maximo_automatico=Decimal("40"), max_reclamos_periodo=3, periodo_dias=30
)


def regla(
    solucion: SolucionCompensacion = SolucionCompensacion.REEMBOLSO_PARCIAL,
    base_monto: BaseMonto = BaseMonto.ITEMS_AFECTADOS,
    valor: str = "0",
    requiere_foto: bool = False,
    activa: bool = True,
) -> ReglaResolucion:
    return ReglaResolucion(
        tipo=TipoReclamo.PEDIDO_INCOMPLETO,
        solucion=solucion,
        base_monto=base_monto,
        valor=Decimal(valor),
        requiere_foto=requiere_foto,
        activa=activa,
    )


def reclamo(
    afectados: list[tuple[int, str]] | None = None,
    total: str = "82.50",
    foto: str | None = None,
    tipo: TipoReclamo = TipoReclamo.PEDIDO_INCOMPLETO,
) -> Reclamo:
    """Reclamo en memoria: `afectados` son (cantidad afectada, precio unitario)."""
    items = [
        ReclamoItem(cantidad_afectada=cantidad, pedido_item=PedidoItem(precio_unitario=Decimal(p)))
        for cantidad, p in (afectados or [])
    ]
    return Reclamo(tipo=tipo, pedido=Pedido(total=Decimal(total)), items=items, foto_ruta=foto)


# ---------- Monto ----------


@pytest.mark.parametrize(
    ("base", "valor", "afectados", "esperado"),
    [
        (BaseMonto.NINGUNO, "0", [(1, "27.90")], "0.00"),
        (BaseMonto.ITEMS_AFECTADOS, "0", [(1, "27.90"), (2, "6.90")], "41.70"),
        (BaseMonto.FIJO, "10", [], "10.00"),
        (BaseMonto.PORCENTAJE_TOTAL, "15", [], "12.38"),  # 15% de 82.50 = 12.375 → 12.38
        (BaseMonto.TOTAL_PEDIDO, "0", [], "82.50"),
        (BaseMonto.FIJO, "500", [], "82.50"),  # nunca más que el total del pedido
    ],
)
def test_calcular_monto(
    base: BaseMonto, valor: str, afectados: list[tuple[int, str]], esperado: str
) -> None:
    assert calcular_monto(regla(base_monto=base, valor=valor), reclamo(afectados)) == Decimal(
        esperado
    )


# ---------- Controles ----------


def test_reclamo_normal_se_aprueba() -> None:
    decision = evaluar_reclamo(reclamo([(1, "27.90")]), regla(), POLITICA, reclamos_en_periodo=0)
    assert decision.aprobada
    assert decision.solucion == SolucionCompensacion.REEMBOLSO_PARCIAL
    assert decision.monto == Decimal("27.90")
    assert decision.motivo_escalamiento is None


def test_supera_el_monto_maximo_automatico() -> None:
    decision = evaluar_reclamo(reclamo([(2, "27.90")]), regla(), POLITICA, reclamos_en_periodo=0)
    assert not decision.aprobada
    assert decision.monto == Decimal("55.80")
    assert decision.motivo_escalamiento == (
        "Supera el monto máximo automático: S/ 55.80 > S/ 40.00"
    )


def test_justo_en_el_limite_se_aprueba() -> None:
    decision = evaluar_reclamo(reclamo([(1, "40.00")]), regla(), POLITICA, reclamos_en_periodo=0)
    assert decision.aprobada


def test_demasiados_reclamos_en_el_periodo() -> None:
    assert evaluar_reclamo(reclamo([(1, "5")]), regla(), POLITICA, 2).aprobada
    decision = evaluar_reclamo(reclamo([(1, "5")]), regla(), POLITICA, 3)
    assert not decision.aprobada
    assert "ya tiene 3 reclamos en los últimos 30 días (máximo 3)" in str(
        decision.motivo_escalamiento
    )


def test_falta_la_foto_obligatoria() -> None:
    con_foto = regla(requiere_foto=True)
    assert evaluar_reclamo(reclamo([(1, "5")], foto="a.png"), con_foto, POLITICA, 0).aprobada
    decision = evaluar_reclamo(reclamo([(1, "5")]), con_foto, POLITICA, 0)
    assert decision.motivo_escalamiento == "Falta la foto obligatoria para este tipo de reclamo"


def test_reune_todos_los_motivos_para_el_agente() -> None:
    decision = evaluar_reclamo(reclamo([(3, "27.90")]), regla(requiere_foto=True), POLITICA, 5)
    motivo = str(decision.motivo_escalamiento)
    assert "foto" in motivo
    assert "5 reclamos" in motivo
    assert "monto máximo" in motivo


def test_reembolso_sin_productos_afectados_no_se_aprueba() -> None:
    decision = evaluar_reclamo(reclamo([]), regla(), POLITICA, 0)
    assert not decision.aprobada
    assert "monto mayor que cero" in str(decision.motivo_escalamiento)


def test_reenvio_no_tiene_control_de_monto() -> None:
    reenvio = regla(solucion=SolucionCompensacion.REENVIO, base_monto=BaseMonto.NINGUNO)
    decision = evaluar_reclamo(reclamo([(5, "27.90")]), reenvio, POLITICA, 0)
    assert decision.aprobada
    assert decision.monto == Decimal("0.00")


def test_no_se_reembolsa_mas_que_el_saldo_del_pedido() -> None:
    # Pedido de S/ 82.50 con S/ 60.00 ya reembolsados: quedan S/ 22.50.
    decision = evaluar_reclamo(reclamo([(1, "27.90")]), regla(), POLITICA, 0, Decimal("60"))
    assert not decision.aprobada
    assert decision.motivo_escalamiento == (
        "El pedido ya tiene S/ 60.00 reembolsados de S/ 82.50: el saldo (S/ 22.50) "
        "no alcanza para S/ 27.90"
    )
    justo = evaluar_reclamo(reclamo([(1, "22.50")]), regla(), POLITICA, 0, Decimal("60"))
    assert justo.aprobada


def test_el_saldo_solo_limita_reembolsos() -> None:
    """SISCAJA solo limita los reembolsos por el saldo; un cupón o un reenvío no lo usan."""
    cupon = regla(solucion=SolucionCompensacion.CUPON, base_monto=BaseMonto.FIJO, valor="10")
    assert evaluar_reclamo(reclamo(), cupon, POLITICA, 0, Decimal("82.50")).aprobada


@pytest.mark.parametrize("regla_del_tipo", [None, regla(activa=False)])
def test_sin_regla_activa_va_a_revision_humana(regla_del_tipo: ReglaResolucion | None) -> None:
    decision = evaluar_reclamo(reclamo([(1, "5")]), regla_del_tipo, POLITICA, 0)
    assert not decision.aprobada
    assert decision.solucion is None
    assert "No hay una regla activa" in str(decision.motivo_escalamiento)


def test_describir_compensacion() -> None:
    assert describir_compensacion(SolucionCompensacion.REEMBOLSO_PARCIAL, Decimal("18.9")) == (
        "un reembolso de S/ 18.90"
    )
    assert describir_compensacion(SolucionCompensacion.CUPON, Decimal("10")) == (
        "un cupón de S/ 10.00 para tu próximo pedido"
    )
    assert describir_compensacion(SolucionCompensacion.REENVIO, Decimal("0")) == (
        "el reenvío del producto correcto"
    )
    assert formato_soles(Decimal("1234.5")) == "S/ 1,234.50"


# ---------- Con la base de datos ----------


def _reclamo_creado(client: TestClient, db: Session, **datos: Any) -> Reclamo:
    respuesta = crear_reclamo(client, **datos)
    assert respuesta.status_code == 201, respuesta.json()
    return db.scalars(select(Reclamo).where(Reclamo.codigo == respuesta.json()["codigo"])).one()


def test_decidir_con_las_reglas_de_la_base(client: TestClient, db: Session, datos: None) -> None:
    combo = item_id(client, "BY-000101", 0)  # Combo Clásico, S/ 27.90 (pidió 2)
    uno = _reclamo_creado(client, db, items=[{"pedido_item_id": combo, "cantidad_afectada": 1}])
    decision = decidir(db, uno)
    assert decision.aprobada
    assert decision.monto == Decimal("27.90")

    demora = _reclamo_creado(client, db, pedido_codigo="BY-000104", tipo="demora", items=[])
    decision = decidir(db, demora)
    assert decision.aprobada
    assert (decision.solucion, decision.monto) == (SolucionCompensacion.CUPON, Decimal("10.00"))


def test_la_politica_de_la_base_se_respeta(client: TestClient, db: Session, datos: None) -> None:
    db.execute(update(PoliticaAntifraude).values(monto_maximo_automatico=Decimal("20")))
    db.commit()
    combo = item_id(client, "BY-000101", 0)
    reclamo_bd = _reclamo_creado(
        client, db, items=[{"pedido_item_id": combo, "cantidad_afectada": 1}]
    )
    assert decidir(db, reclamo_bd).motivo_escalamiento == (
        "Supera el monto máximo automático: S/ 27.90 > S/ 20.00"
    )


def test_contar_reclamos_en_periodo(client: TestClient, db: Session, datos: None) -> None:
    primero = _reclamo_creado(client, db)
    _reclamo_creado(client, db, pedido_codigo="BY-000104", tipo="demora", items=[])
    viejo = _reclamo_creado(client, db, tipo="demora", items=[])
    viejo.creado_en = ahora_utc() - timedelta(days=31)
    db.commit()

    # Cuenta los OTROS reclamos del cliente dentro de los 30 días: el de BY-000104.
    assert contar_reclamos_en_periodo(db, primero, 30, ahora_utc()) == 1
    # Los reclamos de otro cliente no cuentan.
    _reclamo_creado(
        client, db, pedido_codigo="BY-000106", tipo="demora", items=[], headers=CLIENTE2
    )
    assert contar_reclamos_en_periodo(db, primero, 30, ahora_utc()) == 1


def test_reembolsado_en_pedido(client: TestClient, db: Session, datos: None) -> None:
    combo = item_id(client, "BY-000101", 0)
    uno = [{"pedido_item_id": combo, "cantidad_afectada": 1}]
    primero = _reclamo_creado(client, db, items=uno)
    primero.solucion = SolucionCompensacion.REEMBOLSO_PARCIAL
    primero.monto_compensacion = Decimal("27.90")
    primero.estado = EstadoReclamo.RESUELTO
    db.commit()
    segundo = _reclamo_creado(client, db, items=uno)

    assert reembolsado_en_pedido(db, segundo) == Decimal("27.90")
    # El propio reclamo no cuenta, y uno escalado (sin compensar) tampoco.
    assert reembolsado_en_pedido(db, primero) == Decimal("0")
    segundo.estado = EstadoReclamo.RESUELTO  # solo puede haber uno abierto por tipo
    db.commit()
    primero.estado = EstadoReclamo.ESCALADO
    db.commit()
    assert reembolsado_en_pedido(db, segundo) == Decimal("0")
