"""Montos en soles: redondeo y formato para los mensajes al cliente."""

from decimal import ROUND_HALF_UP, Decimal

CENTIMO = Decimal("0.01")


def redondear(monto: Decimal) -> Decimal:
    return monto.quantize(CENTIMO, rounding=ROUND_HALF_UP)


def formato_soles(monto: Decimal) -> str:
    """Decimal("1234.5") → "S/ 1,234.50"."""
    return f"S/ {redondear(monto):,.2f}"
