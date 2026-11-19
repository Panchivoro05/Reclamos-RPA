"""Interfaz de IA: proveedor simulado y registro de llamadas (costo, latencia, errores)."""

from collections.abc import Callable
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LlamadaIA, OperacionIA, Reclamo, TipoReclamo
from app.services.ia import (
    AnalisisFoto,
    AnalisisTexto,
    EntradaFoto,
    EntradaTexto,
    ErrorIA,
    ProveedorSimulado,
    get_proveedor_ia,
    normalizar,
)
from app.services.ia_registro import costo_usd, llamar
from tests.utils import crear_reclamo

PRODUCTOS = ["Combo Clásico", "Nuggets x6", "Sundae de chocolate"]


def _entrada(descripcion: str, tipo: TipoReclamo = TipoReclamo.PEDIDO_INCOMPLETO) -> EntradaTexto:
    return EntradaTexto(descripcion=descripcion, tipo_elegido=tipo, productos_pedido=PRODUCTOS)


def _clasificar(
    descripcion: str, tipo: TipoReclamo = TipoReclamo.PEDIDO_INCOMPLETO
) -> AnalisisTexto:
    return ProveedorSimulado().clasificar_texto(_entrada(descripcion, tipo)).resultado


def test_normalizar_quita_tildes_y_mayusculas() -> None:
    assert normalizar("Llegó FRÍA") == "llego fria"


@pytest.mark.parametrize(
    ("descripcion", "tipo"),
    [
        ("Me faltaron los nuggets, no vinieron en la bolsa", TipoReclamo.PEDIDO_INCOMPLETO),
        ("Pedí un combo y me trajeron otra hamburguesa", TipoReclamo.PRODUCTO_EQUIVOCADO),
        ("La hamburguesa llegó fría y aplastada", TipoReclamo.MAL_ESTADO),
        ("El pedido se demoró más de dos horas", TipoReclamo.DEMORA),
    ],
)
def test_simulado_clasifica_por_palabras_clave(descripcion: str, tipo: TipoReclamo) -> None:
    analisis = _clasificar(descripcion)

    assert analisis.tipo_detectado is tipo
    assert analisis.confianza == pytest.approx(0.9)


def test_simulado_no_confunde_papas_fritas_ni_ahora() -> None:
    # "fritas" no es "frías" y "ahora" no es "hora".
    analisis = _clasificar("Ahora mismo me doy cuenta: faltan las papas fritas")

    assert analisis.tipo_detectado is TipoReclamo.PEDIDO_INCOMPLETO


def test_simulado_sin_pistas_tiene_confianza_baja() -> None:
    analisis = _clasificar("Hola, quiero hacer un reclamo por favor")

    assert analisis.tipo_detectado is None
    assert analisis.confianza < 0.5


def test_simulado_en_empate_prefiere_el_tipo_elegido() -> None:
    analisis = _clasificar("Llegó tarde y además faltó el sundae", TipoReclamo.DEMORA)

    assert analisis.tipo_detectado is TipoReclamo.DEMORA
    assert analisis.confianza == pytest.approx(0.6)


def test_simulado_detecta_productos_mencionados() -> None:
    analisis = _clasificar("Faltaron los nuggets y el sundae")

    assert analisis.productos_mencionados == ["Nuggets x6", "Sundae de chocolate"]


def test_simulado_acepta_respuestas_a_medida() -> None:
    incoherente = AnalisisFoto(
        es_comida=False, coherente=False, descripcion="Una foto de un gato", confianza=0.95
    )
    proveedor = ProveedorSimulado(foto=lambda _: incoherente)
    entrada = EntradaFoto(b"png", "image/png", TipoReclamo.MAL_ESTADO, "Llegó fría")

    assert proveedor.analizar_foto(entrada).resultado == incoherente
    assert proveedor.entradas_foto == [entrada]


def test_proveedor_por_defecto_es_el_simulado() -> None:
    assert isinstance(get_proveedor_ia(), ProveedorSimulado)


def test_costo_segun_precios_configurados(configurar: Callable[..., None]) -> None:
    configurar(ia_precio_entrada_usd_millon=0.10, ia_precio_salida_usd_millon=0.40)

    # 1 000 tokens de entrada (0.0001) + 500 de salida (0.0002).
    assert costo_usd(1000, 500) == Decimal("0.000300")


def _un_reclamo(client: TestClient, db: Session) -> Reclamo:
    assert crear_reclamo(client).status_code == 201
    return db.scalars(select(Reclamo)).one()


def test_llamar_registra_la_llamada_exitosa(
    client: TestClient, db: Session, datos: None, configurar: Callable[..., None]
) -> None:
    configurar(ia_precio_entrada_usd_millon=1, ia_precio_salida_usd_millon=2)
    reclamo = _un_reclamo(client, db)
    proveedor = ProveedorSimulado()

    analisis = llamar(
        db,
        OperacionIA.CLASIFICAR_TEXTO,
        proveedor.nombre,
        lambda: proveedor.clasificar_texto(_entrada("Faltaron los nuggets")),
        reclamo_id=reclamo.id,
    )
    db.commit()

    llamada = db.scalars(select(LlamadaIA)).one()
    assert llamada.reclamo_id == reclamo.id
    assert llamada.operacion is OperacionIA.CLASIFICAR_TEXTO
    assert (llamada.proveedor, llamada.modelo) == ("simulado", "palabras-clave")
    assert llamada.exito and llamada.error is None
    assert llamada.tokens_entrada > 0 and llamada.tokens_salida > 0
    assert llamada.latencia_ms >= 0
    assert llamada.costo_usd > 0
    assert llamada.resultado == analisis.model_dump(mode="json")
    assert llamada.resultado["tipo_detectado"] == "pedido_incompleto"


def test_llamar_registra_el_error_y_lo_relanza(
    client: TestClient, db: Session, datos: None
) -> None:
    reclamo = _un_reclamo(client, db)

    def fallar(_: EntradaTexto) -> AnalisisTexto:
        raise ErrorIA("429: cuota agotada")

    proveedor = ProveedorSimulado(texto=fallar)

    with pytest.raises(ErrorIA, match="cuota"):
        llamar(
            db,
            OperacionIA.CLASIFICAR_TEXTO,
            proveedor.nombre,
            lambda: proveedor.clasificar_texto(_entrada("x")),
            reclamo_id=reclamo.id,
        )
    db.commit()

    llamada = db.scalars(select(LlamadaIA)).one()
    assert not llamada.exito
    assert llamada.error == "429: cuota agotada"
    assert llamada.resultado is None
    assert llamada.costo_usd == 0


def test_las_llamadas_se_borran_con_el_reclamo(
    client: TestClient, db: Session, datos: None
) -> None:
    reclamo = _un_reclamo(client, db)
    proveedor = ProveedorSimulado()
    llamar(
        db,
        OperacionIA.CLASIFICAR_TEXTO,
        proveedor.nombre,
        lambda: proveedor.clasificar_texto(_entrada("Faltó el sundae")),
        reclamo_id=reclamo.id,
    )
    db.commit()

    db.delete(reclamo)
    db.commit()

    assert db.scalars(select(LlamadaIA)).all() == []
