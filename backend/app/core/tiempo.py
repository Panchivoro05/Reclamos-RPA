from datetime import UTC, datetime
from zoneinfo import ZoneInfo

ZONA_LIMA = ZoneInfo("America/Lima")


def ahora_utc() -> datetime:
    return datetime.now(UTC)


def formato_lima(momento: datetime) -> str:
    """Fecha legible para el cliente: 23/10/2026 18:04."""
    return momento.astimezone(ZONA_LIMA).strftime("%d/%m/%Y %H:%M")
