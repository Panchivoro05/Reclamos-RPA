"""Reglas de resolución y política antifraude configurables en la base de datos."""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    BaseMonto,
    PoliticaAntifraude,
    ReglaResolucion,
    SolucionCompensacion,
    TipoReclamo,
)
from app.services import reglas
from tests.utils import CLIENTE1, crear_reclamo


def test_la_migracion_carga_las_reglas_y_limites_acordados(db: Session) -> None:
    demora = reglas.obtener_regla(db, TipoReclamo.DEMORA)
    assert demora is not None
    assert demora.solucion == SolucionCompensacion.CUPON
    assert demora.base_monto == BaseMonto.FIJO
    assert demora.valor == Decimal("10.00")

    incompleto = reglas.obtener_regla(db, TipoReclamo.PEDIDO_INCOMPLETO)
    assert incompleto is not None
    assert incompleto.solucion == SolucionCompensacion.REEMBOLSO_PARCIAL
    assert incompleto.base_monto == BaseMonto.ITEMS_AFECTADOS

    politica = reglas.obtener_politica(db)
    assert politica.monto_maximo_automatico == Decimal("40.00")
    assert politica.max_reclamos_periodo == 3
    assert politica.periodo_dias == 30

    assert reglas.tipos_con_foto_obligatoria(db) == [
        TipoReclamo.PRODUCTO_EQUIVOCADO,
        TipoReclamo.MAL_ESTADO,
    ]


def test_detalle_del_pedido_informa_que_tipos_requieren_foto(
    client: TestClient, datos: None
) -> None:
    pedido = client.get("/api/v1/pedidos/BY-000101", headers=CLIENTE1).json()
    assert pedido["tipos_con_foto_obligatoria"] == ["producto_equivocado", "mal_estado"]


def test_la_foto_obligatoria_sale_de_la_tabla(
    client: TestClient, db: Session, datos: None, foto_png: bytes
) -> None:
    # Se exige foto para "pedido incompleto" y se deja de exigir para "mal estado".
    incompleto = db.get(ReglaResolucion, TipoReclamo.PEDIDO_INCOMPLETO)
    mal_estado = db.get(ReglaResolucion, TipoReclamo.MAL_ESTADO)
    assert incompleto is not None and mal_estado is not None
    incompleto.requiere_foto = True
    mal_estado.requiere_foto = False
    db.commit()

    respuesta = crear_reclamo(client, tipo="pedido_incompleto")
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "foto_requerida"

    assert crear_reclamo(client, tipo="mal_estado").status_code == 201

    pedido = client.get("/api/v1/pedidos/BY-000104", headers=CLIENTE1).json()
    assert pedido["tipos_con_foto_obligatoria"] == ["producto_equivocado", "pedido_incompleto"]


def test_asegurar_configuracion_no_pisa_cambios_salvo_que_se_pida(db: Session) -> None:
    politica = db.get(PoliticaAntifraude, 1)
    assert politica is not None
    politica.monto_maximo_automatico = Decimal("99")
    db.delete(db.get(ReglaResolucion, TipoReclamo.DEMORA))
    db.commit()

    reglas.asegurar_configuracion(db)
    db.expire_all()
    assert reglas.obtener_politica(db).monto_maximo_automatico == Decimal("99.00")
    assert reglas.obtener_regla(db, TipoReclamo.DEMORA) is not None  # la que faltaba se crea

    reglas.asegurar_configuracion(db, restablecer=True)
    db.expire_all()
    assert reglas.obtener_politica(db).monto_maximo_automatico == Decimal("40.00")


def test_sin_politica_se_usan_los_limites_por_defecto(db: Session) -> None:
    db.delete(db.get(PoliticaAntifraude, 1))
    db.commit()
    politica = reglas.obtener_politica(db)
    assert politica.monto_maximo_automatico == Decimal("40")
    assert politica.max_reclamos_periodo == 3
