"""Código de comisión de la escuela: carrera, turno, cuatrimestre, división y modalidad (ACT4AP)."""

import re

from davincihub.utiles import sin_acentos

PATRON = re.compile(r"(?P<carrera>[A-Z]{2})(?P<turno>[MTN])(?P<cuatrimestre>1[0-2]|[1-9])(?P<division>[A-Z])(?P<modalidad>[PV])")
PATRON_CODIGO = re.compile(r"[A-Z]{2}")
TURNOS = {"M": "Mañana", "T": "Tarde", "N": "Noche"}
MODALIDADES = {"P": "Presencial", "V": "Virtual"}
EJEMPLO = "ACT4AP"

CODIGOS_CONOCIDOS = {
    "diseno multimedial": "DM",
    "diseno y programacion de videojuegos": "DV",
    "diseno y programacion web": "DW",
    "diseno grafico": "DG",
    "cine de animacion y posproduccion": "CA",
    "cine y nuevos formatos audiovisuales": "CF",
    "analista de sistemas": "AC",
    "marketing y negocios digitales con inteligencia artificial": "MD",
}
_CONECTORES = {"de", "del", "y", "e", "con", "en", "la", "el", "los", "las"}


def normalizar(texto) -> str:
    return re.sub(r"\s+", "", str(texto or "")).upper()


def partes(comision) -> dict | None:
    coincidencia = PATRON.fullmatch(normalizar(comision))
    if coincidencia is None:
        return None
    datos = coincidencia.groupdict()
    datos["cuatrimestre"] = int(datos["cuatrimestre"])
    return datos


def anio(comision) -> int | None:
    datos = partes(comision)
    return (datos["cuatrimestre"] + 1) // 2 if datos else None


def error(comision, carrera: dict) -> str | None:
    datos = partes(comision)
    if datos is None:
        return f"Usá el código de tu comisión, por ejemplo {EJEMPLO}: carrera, turno (M, T o N), cuatrimestre, división y modalidad (P o V)."
    if carrera.get("codigo") and datos["carrera"] != carrera["codigo"]:
        return f"Las comisiones de {carrera['nombre']} empiezan con {carrera['codigo']}."
    maximo = (carrera.get("duracion_anios") or 6) * 2
    if datos["cuatrimestre"] > maximo:
        return f"{carrera['nombre']} tiene {maximo} cuatrimestres."
    return None


def detalle(comision) -> str:
    datos = partes(comision)
    if datos is None:
        return ""
    return (f"Turno {TURNOS[datos['turno']].lower()} · {datos['cuatrimestre']}.º cuatrimestre"
            f" · división {datos['division']} · {MODALIDADES[datos['modalidad']].lower()}")


def codigo_sugerido(nombre: str, usados: set[str]) -> str:
    conocido = CODIGOS_CONOCIDOS.get(sin_acentos(nombre).strip())
    if conocido and conocido not in usados:
        return conocido
    letras = re.sub(r"[^A-Z ]", "", sin_acentos(nombre).upper())
    palabras = [p for p in letras.split() if p.lower() not in _CONECTORES] or ["X"]
    candidatos = []
    if len(palabras) > 1:
        candidatos.append(palabras[0][0] + palabras[1][0])
    candidatos += [palabras[0][0] + letra for letra in "".join(palabras)[1:]]
    candidatos += [a + b for a in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for b in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
    return next(c for c in candidatos if len(c) == 2 and c not in usados)


def armar(codigo: str, cuatrimestre: int, anterior=None, semilla: int = 0) -> str:
    datos = partes(anterior)
    texto = normalizar(anterior)
    if datos:
        turno, division, modalidad = datos["turno"], datos["division"], datos["modalidad"]
    else:
        turno = "N" if texto == "TN" else "MTN"[semilla % 3]
        division = texto if re.fullmatch(r"[A-Z]", texto) else "A"
        modalidad = "P"
    return f"{codigo}{turno}{cuatrimestre}{division}{modalidad}"
