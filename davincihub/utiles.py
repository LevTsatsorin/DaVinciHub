import unicodedata
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

ZONA_LOCAL = ZoneInfo("America/Argentina/Buenos_Aires")


def tipo_imagen(contenido: bytes) -> str | None:
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if contenido.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if contenido.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp"
    return None


def ahora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def ahora_local() -> str:
    """Hora de pared de Buenos Aires, sin zona: el mismo formato en que se guardan las reservas."""
    return datetime.now(ZONA_LOCAL).replace(tzinfo=None).isoformat(timespec="seconds")


def a_hora_local(momento: datetime) -> datetime:
    if momento.tzinfo is not None:
        momento = momento.astimezone(ZONA_LOCAL)
    return momento.replace(tzinfo=None)


def hoy_local() -> str:
    return ahora_local()[:10]


def fecha_corta(iso: str) -> str:
    momento = datetime.fromisoformat(iso)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=ZONA_LOCAL)
    return momento.astimezone(ZONA_LOCAL).strftime("%d/%m %H:%M")


def sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.casefold()) if not unicodedata.combining(c))
