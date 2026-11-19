"""Lectura de las reglas de resolución y de la política antifraude (tablas configurables)."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BaseMonto,
    PoliticaAntifraude,
    ReglaResolucion,
    SolucionCompensacion,
    TipoReclamo,
)

# Mismos valores que carga la migración 3d347c3006ec. Aquí sirven para restaurarlos en las
# pruebas y para que el seed los cree si alguien vació las tablas.
REGLAS_POR_DEFECTO: dict[TipoReclamo, tuple[SolucionCompensacion, BaseMonto, Decimal, bool]] = {
    TipoReclamo.PRODUCTO_EQUIVOCADO: (
        SolucionCompensacion.REENVIO,
        BaseMonto.NINGUNO,
        Decimal("0"),
        True,
    ),
    TipoReclamo.PEDIDO_INCOMPLETO: (
        SolucionCompensacion.REEMBOLSO_PARCIAL,
        BaseMonto.ITEMS_AFECTADOS,
        Decimal("0"),
        False,
    ),
    TipoReclamo.MAL_ESTADO: (
        SolucionCompensacion.REEMBOLSO_PARCIAL,
        BaseMonto.ITEMS_AFECTADOS,
        Decimal("0"),
        True,
    ),
    TipoReclamo.DEMORA: (SolucionCompensacion.CUPON, BaseMonto.FIJO, Decimal("10"), False),
}
POLITICA_POR_DEFECTO = {
    "monto_maximo_automatico": Decimal("40"),
    "max_reclamos_periodo": 3,
    "periodo_dias": 30,
}


def obtener_regla(session: Session, tipo: TipoReclamo) -> ReglaResolucion | None:
    return session.get(ReglaResolucion, tipo)


def tipos_con_foto_obligatoria(session: Session) -> list[TipoReclamo]:
    """Tipos cuya regla exige foto. La API y la app usan esta misma fuente."""
    filas = session.scalars(
        select(ReglaResolucion.tipo).where(ReglaResolucion.requiere_foto.is_(True))
    )
    return sorted(filas, key=list(TipoReclamo).index)


def obtener_politica(session: Session) -> PoliticaAntifraude:
    politica = session.get(PoliticaAntifraude, 1)
    if politica is None:
        # Sin política configurada se usan los valores por defecto (nunca "sin límites").
        return PoliticaAntifraude(id=1, **POLITICA_POR_DEFECTO)
    return politica


def asegurar_configuracion(session: Session, *, restablecer: bool = False) -> None:
    """Crea las reglas y la política que falten. Con restablecer=True, las deja por defecto."""
    for tipo, (solucion, base_monto, valor, requiere_foto) in REGLAS_POR_DEFECTO.items():
        regla = session.get(ReglaResolucion, tipo)
        if regla is None:
            session.add(
                ReglaResolucion(
                    tipo=tipo,
                    solucion=solucion,
                    base_monto=base_monto,
                    valor=valor,
                    requiere_foto=requiere_foto,
                    activa=True,
                )
            )
        elif restablecer:
            regla.solucion, regla.base_monto, regla.valor = solucion, base_monto, valor
            regla.requiere_foto, regla.activa = requiere_foto, True

    politica = session.get(PoliticaAntifraude, 1)
    if politica is None:
        session.add(PoliticaAntifraude(id=1, **POLITICA_POR_DEFECTO))
    elif restablecer:
        for campo, valor_politica in POLITICA_POR_DEFECTO.items():
            setattr(politica, campo, valor_politica)
    session.commit()
