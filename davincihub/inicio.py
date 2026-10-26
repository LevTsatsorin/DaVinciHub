from datetime import datetime, timedelta

from davincihub import db
from davincihub.actividades import datos as actividades
from davincihub.objetos import datos as objetos
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


DIAS_SEMANA = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
POR_DIA = 1


def _semana(usuario_id: int, ahora: str) -> list[dict]:
    hoy = datetime.fromisoformat(ahora).date()
    dias = [hoy + timedelta(days=i) for i in range(14)]
    hasta = (dias[-1] + timedelta(days=1)).isoformat()
    eventos = []
    vistas = set()
    for actividad in actividades.listar_actividades_creador(usuario_id):
        if actividad["estado"] in ("aprobada", "pendiente") and ahora[:10] <= actividad["inicio"][:10] < hasta:
            vistas.add(actividad["id"])
            eventos.append({"tipo": "organizo", "inicio": actividad["inicio"], "titulo": actividad["nombre"],
                            "detalle": "Organizás" + (" · en revisión" if actividad["estado"] == "pendiente" else ""),
                            "enlace": ("actividades.detalle", {"actividad_id": actividad["id"]})})
    for actividad in actividades.listar_inscripciones_de(usuario_id):
        if actividad["estado"] == "aprobada" and ahora[:10] <= actividad["inicio"][:10] < hasta and actividad["id"] not in vistas:
            vistas.add(actividad["id"])
            eventos.append({"tipo": "anotado", "inicio": actividad["inicio"], "titulo": actividad["nombre"],
                            "detalle": actividad.get("ubicacion") or "Te anotaste",
                            "enlace": ("actividades.detalle", {"actividad_id": actividad["id"]})})
    for reserva in reservas.listar_reservas_usuario(usuario_id, solo_futuras=True):
        if reserva["actividad_id"] or reserva["inicio"][:10] >= hasta:
            continue
        eventos.append({"tipo": "reserva", "inicio": reserva["inicio"], "titulo": reserva["espacio_nombre"],
                        "detalle": reserva["motivo"] or "Reserva", "enlace": ("espacios.mis_reservas", {})})
    semana = []
    for dia in dias:
        del_dia = sorted((e for e in eventos if e["inicio"][:10] == dia.isoformat()),
                         key=lambda e: e["inicio"])
        semana.append({"fecha": dia, "nombre": "Hoy" if dia == hoy else DIAS_SEMANA[dia.weekday()],
                       "numero": dia.day, "eventos": del_dia[:POR_DIA], "mas": max(0, len(del_dia) - POR_DIA),
                       "total": len(del_dia), "mes": dia.strftime("%Y-%m"), "iso": dia.isoformat()})
    return semana


def _numeros(usuario_id: int) -> dict:
    return dict(db.query_one(
        "SELECT"
        " (SELECT COUNT(*) FROM preguntas WHERE autor_id = :yo) AS preguntas,"
        " (SELECT COUNT(*) FROM respuestas WHERE autor_id = :yo) AS respuestas,"
        " (SELECT COUNT(*) FROM valoraciones_respuestas v JOIN respuestas r ON r.id = v.respuesta_id"
        "  WHERE r.autor_id = :yo) AS utiles,"
        " (SELECT COUNT(*) FROM publicaciones WHERE autor_id = :yo AND estado = 'activa') AS publicaciones,"
        " (SELECT COUNT(*) FROM conexiones WHERE (solicitante_id = :yo OR receptor_id = :yo)"
        "  AND estado = 'aceptada') AS conexiones",
        yo=usuario_id,
    ))


def _preguntas_para_ayudar(usuario: dict) -> list[dict]:
    return db.query(
        "SELECT p.id, p.titulo, p.creado, m.nombre AS materia, u.nombre AS autor_nombre, u.apellido AS autor_apellido"
        " FROM preguntas p JOIN materias m ON m.id = p.materia_id JOIN usuarios u ON u.id = p.autor_id"
        " WHERE m.carrera_id = :carrera AND p.autor_id <> :yo AND u.bloqueado = 0"
        " AND NOT EXISTS (SELECT 1 FROM respuestas r WHERE r.pregunta_id = p.id)"
        " ORDER BY p.creado DESC LIMIT 4",
        carrera=usuario["carrera_id"] or 0, yo=usuario["id"],
    )


def _objetos_destacados(usuario: dict) -> list[dict]:
    return db.query(
        "SELECT p.id, p.titulo, p.categoria, p.modalidad, p.precio, p.estado_objeto, p.autor_id, p.creado,"
        " u.nombre AS autor_nombre, u.apellido AS autor_apellido, c.nombre AS carrera"
        " FROM publicaciones p JOIN usuarios u ON u.id = p.autor_id LEFT JOIN carreras c ON c.id = p.carrera_id"
        " WHERE p.estado = 'activa' AND u.bloqueado = 0 AND p.autor_id <> :yo"
        " ORDER BY CASE WHEN p.carrera_id = :carrera THEN 0 ELSE 1 END, p.creado DESC, p.id DESC LIMIT 3",
        yo=usuario["id"], carrera=usuario["carrera_id"] or 0,
    )


def _sugerencias(usuario: dict) -> list[dict]:
    return db.query(
        "SELECT u.id, u.nombre, u.apellido, u.anio, u.comision, u.carrera_id, c.nombre AS carrera,"
        " EXISTS (SELECT 1 FROM fotos_perfil f WHERE f.usuario_id = u.id) AS tiene_foto"
        " FROM usuarios u LEFT JOIN carreras c ON c.id = u.carrera_id"
        " WHERE u.rol = 'estudiante' AND u.bloqueado = 0 AND u.id <> :yo"
        " AND NOT EXISTS (SELECT 1 FROM conexiones x WHERE (x.solicitante_id = :yo AND x.receptor_id = u.id)"
        "                 OR (x.solicitante_id = u.id AND x.receptor_id = :yo))"
        " ORDER BY CASE WHEN u.carrera_id = :carrera THEN 0 ELSE 1 END, CASE WHEN u.anio = :anio THEN 0 ELSE 1 END,"
        " CASE WHEN u.comision = :comision THEN 0 ELSE 1 END, u.apellido, u.nombre LIMIT 3",
        yo=usuario["id"], carrera=usuario["carrera_id"] or 0, anio=usuario["anio"] or 0,
        comision=usuario["comision"] or "",
    )


def _resumen(usuario_id: int) -> dict:
    fila = db.query_one(
        "SELECT"
        " (SELECT COUNT(*) FROM mensajes WHERE receptor_id = :yo AND leido = 0) AS mensajes,"
        " (SELECT COUNT(*) FROM conexiones WHERE receptor_id = :yo AND estado = 'pendiente') AS solicitudes,"
        " (SELECT COUNT(*) FROM notificaciones WHERE usuario_id = :yo AND leida = 0 AND tipo = 'foro') AS respuestas,"
        " (SELECT COUNT(*) FROM coincidencias c JOIN solicitudes s ON s.id = c.solicitud_id"
        "  JOIN publicaciones p ON p.id = c.publicacion_id"
        "  WHERE s.autor_id = :yo AND s.estado = 'activa' AND p.estado = 'activa') AS coincidencias",
        yo=usuario_id,
    )
    return dict(fila)


def contexto(usuario: dict | None) -> dict:
    datos = {"proximas": actividades.listar_actividades_publicas(limite=EN_AGENDA), "ahora": ahora_local()}
    if usuario is None:
        return datos
    datos["mis_reservas"] = reservas.listar_reservas_usuario(usuario["id"], solo_futuras=True)[:EN_AGENDA]
    datos["mis_actividades"] = _mis_actividades(usuario["id"], datos["ahora"])
    if usuario["rol"] == "admin":
        datos["pendientes"] = _pendientes_admin()
        return datos
    datos.update(
        resumen=_resumen(usuario["id"]),
        semana=_semana(usuario["id"], datos["ahora"]),
        numeros=_numeros(usuario["id"]),
        para_ayudar=_preguntas_para_ayudar(usuario),
        objetos_destacados=_objetos_destacados(usuario),
        sugerencias=_sugerencias(usuario),
        categorias=objetos.CATEGORIAS, modalidades=objetos.MODALIDADES, condiciones=objetos.CONDICIONES,
    )
    return datos
