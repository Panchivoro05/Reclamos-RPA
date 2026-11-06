"""Compensaciones: reglas del sistema de caja y registro con número de operación."""

import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from caja.db import obtener_db
from caja.formato import ahora_utc_iso, soles
from caja.pedidos import Pedido

MOTIVO_MIN = 10
MOTIVO_MAX = 500


class TipoCompensacion(StrEnum):
    REENVIO = "reenvio"
    REEMBOLSO_PARCIAL = "reembolso_parcial"
    REEMBOLSO_TOTAL = "reembolso_total"
    CUPON = "cupon"

    @property
    def texto(self) -> str:
        return {
            "reenvio": "REENVIO DE PRODUCTO",
            "reembolso_parcial": "REEMBOLSO PARCIAL",
            "reembolso_total": "REEMBOLSO TOTAL",
            "cupon": "CUPON DE DESCUENTO",
        }[self.value]

    @property
    def es_reembolso(self) -> bool:
        return self in (TipoCompensacion.REEMBOLSO_PARCIAL, TipoCompensacion.REEMBOLSO_TOTAL)


class ErrorCompensacion(Exception):
    """La compensación no cumple una regla; el mensaje se muestra al operador."""


@dataclass(frozen=True)
class Compensacion:
    numero: str
    pedido_codigo: str
    tipo: TipoCompensacion
    monto_centimos: int
    motivo: str
    operador: str
    creado_en: str


def saldo_reembolsable(pedido_id: int) -> int:
    """Total del pedido menos lo ya reembolsado (los cupones y reenvíos no cuentan)."""
    fila = (
        obtener_db()
        .execute(
            """
            SELECT p.total_centimos - COALESCE(SUM(c.monto_centimos), 0) AS saldo
            FROM pedidos p
            LEFT JOIN compensaciones c
              ON c.pedido_id = p.id AND c.tipo IN ('reembolso_parcial', 'reembolso_total')
            WHERE p.id = ?
            GROUP BY p.id
            """,
            (pedido_id,),
        )
        .fetchone()
    )
    return int(fila["saldo"]) if fila else 0


def leer_monto(texto: str) -> int:
    """'12.5' → 1250 céntimos. Acepta coma decimal y el prefijo 'S/'."""
    limpio = texto.strip().upper().removeprefix("S/").strip().replace(",", ".")
    if not limpio:
        raise ErrorCompensacion("Ingrese el monto.")
    try:
        valor = Decimal(limpio)
    except InvalidOperation:
        raise ErrorCompensacion(f"Monto invalido: {texto.strip()}.") from None
    if not valor.is_finite():
        raise ErrorCompensacion(f"Monto invalido: {texto.strip()}.")
    if valor <= 0:
        raise ErrorCompensacion("El monto debe ser mayor que cero.")
    if valor != valor.quantize(Decimal("0.01")):
        raise ErrorCompensacion("El monto admite como maximo 2 decimales.")
    return int(valor * 100)


def registrar_compensacion(
    pedido: Pedido, tipo_texto: str, monto_texto: str, motivo: str, operador_id: int
) -> Compensacion:
    """Valida las reglas y guarda la compensación. Lanza ErrorCompensacion si algo falla."""
    try:
        tipo = TipoCompensacion(tipo_texto)
    except ValueError:
        raise ErrorCompensacion("Seleccione el tipo de compensacion.") from None

    motivo = " ".join(motivo.split())
    if len(motivo) < MOTIVO_MIN:
        raise ErrorCompensacion(f"El motivo debe tener al menos {MOTIVO_MIN} caracteres.")
    if len(motivo) > MOTIVO_MAX:
        raise ErrorCompensacion(f"El motivo admite como maximo {MOTIVO_MAX} caracteres.")
    if pedido.estado == "cancelado":
        raise ErrorCompensacion(
            f"El pedido {pedido.codigo} esta cancelado: no admite compensaciones."
        )

    conexion = obtener_db()
    # BEGIN IMMEDIATE bloquea la escritura: el saldo y el correlativo no cambian
    # mientras se registra la compensación.
    conexion.execute("BEGIN IMMEDIATE")
    try:
        saldo = saldo_reembolsable(pedido.id)
        match tipo:
            case TipoCompensacion.REENVIO:
                monto = 0  # se reenvía el producto, no hay dinero de por medio
            case TipoCompensacion.REEMBOLSO_TOTAL:
                if saldo <= 0:
                    raise ErrorCompensacion(
                        f"El pedido {pedido.codigo} ya fue reembolsado por completo."
                    )
                monto = saldo
            case TipoCompensacion.REEMBOLSO_PARCIAL:
                monto = leer_monto(monto_texto)
                if monto > saldo:
                    raise ErrorCompensacion(
                        f"Monto excedido: el maximo reembolsable es {soles(saldo)}."
                    )
            case TipoCompensacion.CUPON:
                monto = leer_monto(monto_texto)
                if monto > pedido.total_centimos:
                    raise ErrorCompensacion(
                        f"Monto excedido: el cupon no puede superar el total del pedido "
                        f"({soles(pedido.total_centimos)})."
                    )

        numero = _siguiente_numero(conexion)
        conexion.execute(
            """
            INSERT INTO compensaciones
                (numero, pedido_id, tipo, monto_centimos, motivo, operador_id, creado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (numero, pedido.id, tipo.value, monto, motivo, operador_id, ahora_utc_iso()),
        )
        conexion.commit()
    except BaseException:
        conexion.rollback()
        raise

    compensacion = obtener_compensacion(numero)
    assert compensacion is not None
    return compensacion


def _siguiente_numero(conexion: sqlite3.Connection) -> str:
    fila = conexion.execute("SELECT COALESCE(MAX(id), 0) + 1 AS siguiente FROM compensaciones")
    return f"CMP-{fila.fetchone()['siguiente']:06d}"


_CONSULTA = """
    SELECT c.numero, p.codigo AS pedido_codigo, c.tipo, c.monto_centimos, c.motivo,
           o.usuario AS operador, c.creado_en
    FROM compensaciones c
    JOIN pedidos p ON p.id = c.pedido_id
    JOIN operadores o ON o.id = c.operador_id
"""


def _armar(fila: sqlite3.Row) -> Compensacion:
    return Compensacion(
        numero=fila["numero"],
        pedido_codigo=fila["pedido_codigo"],
        tipo=TipoCompensacion(fila["tipo"]),
        monto_centimos=fila["monto_centimos"],
        motivo=fila["motivo"],
        operador=fila["operador"],
        creado_en=fila["creado_en"],
    )


def obtener_compensacion(numero: str) -> Compensacion | None:
    fila = obtener_db().execute(f"{_CONSULTA} WHERE c.numero = ?", (numero.upper(),)).fetchone()
    return _armar(fila) if fila else None


def listar_por_pedido(pedido_id: int) -> list[Compensacion]:
    filas = obtener_db().execute(f"{_CONSULTA} WHERE c.pedido_id = ? ORDER BY c.id", (pedido_id,))
    return [_armar(fila) for fila in filas]


def listar_recientes(limite: int = 100) -> list[Compensacion]:
    filas = obtener_db().execute(f"{_CONSULTA} ORDER BY c.id DESC LIMIT ?", (limite,))
    return [_armar(fila) for fila in filas]
