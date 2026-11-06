"""Formatos para mostrar: soles y fechas en hora de Lima."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

ZONA_LIMA = ZoneInfo("America/Lima")


def ahora_utc_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def soles(centimos: int) -> str:
    """1234 → "S/ 12.34"."""
    signo = "-" if centimos < 0 else ""
    centimos = abs(centimos)
    return f"{signo}S/ {centimos // 100:,}.{centimos % 100:02d}"


def fecha_lima(iso: str | None) -> str:
    """Fecha ISO en UTC → "27/10/2026 14:05" en hora de Lima ("-" si no hay fecha)."""
    if not iso:
        return "-"
    fecha = datetime.fromisoformat(iso)
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=UTC)
    return fecha.astimezone(ZONA_LIMA).strftime("%d/%m/%Y %H:%M")
