from datetime import UTC, datetime
from zoneinfo import ZoneInfo

ZONA_LOCAL = ZoneInfo("America/Argentina/Buenos_Aires")


def ahora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def fecha_corta(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(ZONA_LOCAL).strftime("%d/%m %H:%M")
