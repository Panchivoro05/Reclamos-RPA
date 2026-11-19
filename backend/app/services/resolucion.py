"""Motor de reglas y controles antifraude: decide si un reclamo se resuelve solo y cómo.

`evaluar_reclamo` es una función pura (sin base de datos): recibe el reclamo, su regla, la
política y el historial del cliente, y devuelve una `Decision`. Así cada regla se prueba y se
explica por separado. `decidir` solo junta esos datos desde la base.

La IA (fase 5) nunca decide montos: los montos salen siempre de estas reglas.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.moneda import formato_soles, redondear
from app.core.tiempo import ahora_utc
from app.models import (
    BaseMonto,
    EstadoReclamo,
    PoliticaAntifraude,
    Reclamo,
    ReglaResolucion,
    SolucionCompensacion,
)
from app.services.reglas import obtener_politica, obtener_regla

SOLUCIONES_REEMBOLSO = frozenset(
    {SolucionCompensacion.REEMBOLSO_PARCIAL, SolucionCompensacion.REEMBOLSO_TOTAL}
)
# Reclamos cuya compensación ya está aprobada o registrada (cuentan para el saldo del pedido).
ESTADOS_COMPENSADOS = frozenset(
    {
        EstadoReclamo.VALIDADO,
        EstadoReclamo.EN_RESOLUCION,
        EstadoReclamo.RESUELTO,
        EstadoReclamo.CERRADO,
    }
)

SOLUCIONES_CON_DINERO = frozenset(
    {
        SolucionCompensacion.REEMBOLSO_PARCIAL,
        SolucionCompensacion.REEMBOLSO_TOTAL,
        SolucionCompensacion.CUPON,
    }
)


@dataclass(frozen=True)
class Control:
    nombre: str
    aprobado: bool
    detalle: str


@dataclass(frozen=True)
class Decision:
    solucion: SolucionCompensacion | None
    monto: Decimal
    controles: list[Control] = field(default_factory=list)

    @property
    def aprobada(self) -> bool:
        return self.solucion is not None and all(c.aprobado for c in self.controles)

    @property
    def motivo_escalamiento(self) -> str | None:
        """Texto interno para el agente: todos los controles que fallaron."""
        fallidos = [c.detalle for c in self.controles if not c.aprobado]
        return "; ".join(fallidos) if fallidos else None


def calcular_monto(regla: ReglaResolucion, reclamo: Reclamo) -> Decimal:
    """Monto de la compensación según la base de la regla (nunca más que el total del pedido)."""
    total = reclamo.pedido.total
    match regla.base_monto:
        case BaseMonto.NINGUNO:
            return Decimal("0.00")
        case BaseMonto.ITEMS_AFECTADOS:
            monto = sum(
                (
                    item.cantidad_afectada * item.pedido_item.precio_unitario
                    for item in reclamo.items
                ),
                Decimal("0"),
            )
        case BaseMonto.FIJO:
            monto = regla.valor
        case BaseMonto.PORCENTAJE_TOTAL:
            monto = total * regla.valor / 100
        case BaseMonto.TOTAL_PEDIDO:
            monto = total
    return redondear(min(monto, total))


def evaluar_reclamo(
    reclamo: Reclamo,
    regla: ReglaResolucion | None,
    politica: PoliticaAntifraude,
    reclamos_en_periodo: int,
    ya_reembolsado: Decimal = Decimal("0"),
) -> Decision:
    """Aplica la regla y TODOS los controles (el agente ve cada motivo, no solo el primero).

    `reclamos_en_periodo` son los OTROS reclamos del cliente en los últimos días de la política.
    `ya_reembolsado` es lo que otros reclamos ya devolvieron (o van a devolver) de este pedido.
    """
    if regla is None or not regla.activa:
        return Decision(
            solucion=None,
            monto=Decimal("0.00"),
            controles=[
                Control(
                    "regla",
                    False,
                    f"No hay una regla activa para el tipo {reclamo.tipo.value}: "
                    "requiere revisión humana",
                )
            ],
        )

    monto = calcular_monto(regla, reclamo)
    controles = [Control("regla", True, f"Regla del tipo {reclamo.tipo.value}")]

    if regla.requiere_foto:
        controles.append(
            Control("foto", True, "Tiene foto")
            if reclamo.foto_ruta
            else Control("foto", False, "Falta la foto obligatoria para este tipo de reclamo")
        )

    maximo = politica.max_reclamos_periodo
    if reclamos_en_periodo >= maximo:
        controles.append(
            Control(
                "frecuencia",
                False,
                f"El cliente ya tiene {reclamos_en_periodo} reclamos en los últimos "
                f"{politica.periodo_dias} días (máximo {maximo})",
            )
        )
    else:
        controles.append(
            Control("frecuencia", True, f"{reclamos_en_periodo} reclamos previos en el periodo")
        )

    if regla.solucion in SOLUCIONES_CON_DINERO:
        if monto <= 0:
            controles.append(
                Control(
                    "monto",
                    False,
                    "No se pudo calcular un monto mayor que cero (¿faltan productos afectados?)",
                )
            )
        elif monto > politica.monto_maximo_automatico:
            controles.append(
                Control(
                    "monto",
                    False,
                    f"Supera el monto máximo automático: {formato_soles(monto)} > "
                    f"{formato_soles(politica.monto_maximo_automatico)}",
                )
            )
        else:
            controles.append(
                Control("monto", True, f"Monto {formato_soles(monto)} dentro del límite")
            )

    if regla.solucion in SOLUCIONES_REEMBOLSO:
        controles.append(_control_saldo(reclamo.pedido.total, ya_reembolsado, monto))

    return Decision(solucion=regla.solucion, monto=monto, controles=controles)


def _control_saldo(total: Decimal, ya_reembolsado: Decimal, monto: Decimal) -> Control:
    """Lo devuelto de un pedido nunca supera su total (la misma regla que aplica SISCAJA, pero
    revisada antes de lanzar el bot)."""
    saldo = max(total - ya_reembolsado, Decimal("0"))
    if monto > saldo:
        return Control(
            "saldo_pedido",
            False,
            f"El pedido ya tiene {formato_soles(ya_reembolsado)} reembolsados de "
            f"{formato_soles(total)}: el saldo ({formato_soles(saldo)}) no alcanza para "
            f"{formato_soles(monto)}",
        )
    return Control("saldo_pedido", True, f"Saldo reembolsable del pedido: {formato_soles(saldo)}")


def contar_reclamos_en_periodo(
    session: Session, reclamo: Reclamo, periodo_dias: int, ahora: datetime
) -> int:
    """Otros reclamos del mismo cliente creados en los últimos `periodo_dias` días."""
    desde = ahora - timedelta(days=periodo_dias)
    consulta = select(func.count(Reclamo.id)).where(
        Reclamo.cliente_id == reclamo.cliente_id,
        Reclamo.id != reclamo.id,
        Reclamo.creado_en >= desde,
    )
    return int(session.scalar(consulta) or 0)


def reembolsado_en_pedido(session: Session, reclamo: Reclamo) -> Decimal:
    """Lo que OTROS reclamos del mismo pedido ya reembolsaron o tienen aprobado reembolsar."""
    consulta = select(func.coalesce(func.sum(Reclamo.monto_compensacion), 0)).where(
        Reclamo.pedido_id == reclamo.pedido_id,
        Reclamo.id != reclamo.id,
        Reclamo.solucion.in_(SOLUCIONES_REEMBOLSO),
        Reclamo.estado.in_(ESTADOS_COMPENSADOS),
    )
    return Decimal(session.scalar(consulta) or 0)


def decidir(session: Session, reclamo: Reclamo, ahora: datetime | None = None) -> Decision:
    politica = obtener_politica(session)
    previos = contar_reclamos_en_periodo(
        session, reclamo, politica.periodo_dias, ahora or ahora_utc()
    )
    return evaluar_reclamo(
        reclamo,
        obtener_regla(session, reclamo.tipo),
        politica,
        previos,
        reembolsado_en_pedido(session, reclamo),
    )


def describir_compensacion(solucion: SolucionCompensacion, monto: Decimal) -> str:
    """Texto para el cliente: "un reembolso de S/ 18.90"."""
    match solucion:
        case SolucionCompensacion.REENVIO:
            return "el reenvío del producto correcto"
        case SolucionCompensacion.REEMBOLSO_PARCIAL | SolucionCompensacion.REEMBOLSO_TOTAL:
            return f"un reembolso de {formato_soles(monto)}"
        case SolucionCompensacion.CUPON:
            return f"un cupón de {formato_soles(monto)} para tu próximo pedido"
