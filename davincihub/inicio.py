from datetime import datetime, timedelta

from davincihub import db
from davincihub.actividades import datos as actividades
from davincihub.reservas import datos as reservas
from davincihub.utiles import ahora_local

EN_AGENDA = 3


def _mis_actividades(usuario_id: int, ahora: str) -> list[dict]:
    """Próximas actividades del estudiante: las que organiza y aquellas en las que se anotó."""
    propias = [
        a | {"rol_mio": "Organizás"} for a in actividades.listar_actividades_creador(usuario_id)
        if a["estado"] in ("aprobada", "pendiente") and (a["fin"] or a["inicio"]) >= ahora
    ]
    anotadas = [
        a | {"rol_mio": "Te anotaste"} for a in actividades.listar_inscripciones_de(usuario_id)
        if a["estado"] == "aprobada" and (a["fin"] or a["inicio"]) >= ahora
    ]
    return sorted(propias + anotadas, key=lambda a: a["inicio"])[:EN_AGENDA]


def _pendientes_admin() -> dict:
    ahora = ahora_local()
    en_una_semana = (datetime.fromisoformat(ahora) + timedelta(days=7)).isoformat(timespec="seconds")
    return {
        "actividades": actividades.contar_actividades_por_estado().get("pendiente", 0),
        "bloqueados": db.query_one("SELECT count(*) AS n FROM usuarios WHERE bloqueado = 1")["n"],
        "reservas_semana": db.query_one(
            "SELECT count(*) AS n FROM reservas WHERE estado = 'confirmada' AND inicio >= :desde AND inicio < :hasta",
            desde=ahora,
            hasta=en_una_semana,
        )["n"],
    }


def contexto(usuario: dict | None) -> dict:
    datos = {"proximas": actividades.listar_actividades_publicas(limite=EN_AGENDA), "ahora": ahora_local()}
    if usuario is None:
        return datos
    datos["mis_reservas"] = reservas.listar_reservas_usuario(usuario["id"], solo_futuras=True)[:EN_AGENDA]
    datos["mis_actividades"] = _mis_actividades(usuario["id"], datos["ahora"])
    if usuario["rol"] == "admin":
        datos["pendientes"] = _pendientes_admin()
    return datos
