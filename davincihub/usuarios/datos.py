from davincihub import db
from davincihub.notificaciones import notificar
from davincihub.utiles import ahora, sin_acentos

LIMITE_MOTIVO = 500
ROLES = ("estudiante", "catedra", "admin")
ESTADOS = ("activo", "bloqueado")


class ErrorUsuario(ValueError):
    """Error base para la administración de usuarios."""


def _filtros_sql(q: str, carrera_id: int | None, rol: str, estado: str) -> tuple[str, dict]:
    condiciones, params = [], {}
    buscado = sin_acentos(q.strip())
    if buscado:
        texto = db.sql_sin_acentos("u.nombre || ' ' || u.apellido || ' ' || u.email")
        condiciones.append(f"{texto} LIKE :buscado ESCAPE '\\'")
        escapado = buscado.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["buscado"] = f"%{escapado}%"
    if carrera_id:
        condiciones.append("u.carrera_id = :carrera")
        params["carrera"] = carrera_id
    if rol in ("estudiante", "admin"):
        condiciones.append("u.rol = :rol")
        params["rol"] = rol
    elif rol == "catedra":
        condiciones.append("u.catedra = 1")
    if estado in ESTADOS:
        condiciones.append("u.bloqueado = :bloqueado")
        params["bloqueado"] = int(estado == "bloqueado")
    return (" WHERE " + " AND ".join(condiciones) if condiciones else ""), params


def listar_usuarios(q: str = "", carrera_id: int | None = None, rol: str = "", estado: str = "",
                    limite: int = 10, salto: int = 0) -> list[dict]:
    donde, params = _filtros_sql(q, carrera_id, rol, estado)
    return db.query(
        "SELECT u.id, u.nombre, u.apellido, u.email, u.rol, u.bloqueado, u.catedra, u.carrera_id, u.anio,"
        " u.comision, c.nombre AS carrera_nombre"
        " FROM usuarios u LEFT JOIN carreras c ON c.id = u.carrera_id"
        f"{donde} ORDER BY u.apellido, u.nombre, u.id LIMIT :limite OFFSET :salto",
        limite=limite, salto=salto, **params,
    )


def contar_usuarios(q: str = "", carrera_id: int | None = None, rol: str = "", estado: str = "") -> int:
    donde, params = _filtros_sql(q, carrera_id, rol, estado)
    return db.query_one(f"SELECT count(*) AS n FROM usuarios u{donde}", **params)["n"]


def obtener_usuario(usuario_id: int) -> dict | None:
    return db.query_one(
        "SELECT u.id, u.nombre, u.apellido, u.email, u.rol, u.bloqueado, u.catedra, u.carrera_id, u.anio,"
        " u.comision, u.creado, c.nombre AS carrera_nombre"
        " FROM usuarios u LEFT JOIN carreras c ON c.id = u.carrera_id WHERE u.id = :id",
        id=usuario_id,
    )


def cambiar_bloqueo(usuario_id: int, admin_id: int, bloquear: bool, motivo: str) -> None:
    """Bloquea o desbloquea una cuenta y deja el registro con el admin y el motivo (RN-15)."""
    motivo = (motivo or "").strip()
    if not motivo:
        raise ErrorUsuario("Escribí el motivo del " + ("bloqueo." if bloquear else "desbloqueo."))
    if len(motivo) > LIMITE_MOTIVO:
        raise ErrorUsuario(f"El motivo admite hasta {LIMITE_MOTIVO} caracteres.")
    if bloquear and usuario_id == admin_id:
        raise ErrorUsuario("No podés bloquearte a vos mismo.")
    with db.transaccion():
        if not db.bloquear_fila("usuarios", usuario_id):
            raise ErrorUsuario("El usuario no existe.")
        usuario = obtener_usuario(usuario_id)
        if bool(usuario["bloqueado"]) == bloquear:
            raise ErrorUsuario("El usuario ya está bloqueado." if bloquear else "El usuario no está bloqueado.")
        db.execute("UPDATE usuarios SET bloqueado = :b WHERE id = :id", b=int(bloquear), id=usuario_id)
        db.execute(
            "INSERT INTO bloqueos (usuario_id, admin_id, accion, motivo, creado)"
            " VALUES (:usuario, :admin, :accion, :motivo, :creado)",
            usuario=usuario_id,
            admin=admin_id,
            accion="bloqueo" if bloquear else "desbloqueo",
            motivo=motivo,
            creado=ahora(),
        )


def historial_bloqueos(usuario_id: int) -> list[dict]:
    return db.query(
        "SELECT b.accion, b.motivo, b.creado, b.admin_id, a.nombre AS admin_nombre, a.apellido AS admin_apellido"
        " FROM bloqueos b JOIN usuarios a ON a.id = b.admin_id"
        " WHERE b.usuario_id = :usuario ORDER BY b.creado DESC, b.id DESC",
        usuario=usuario_id,
    )


def anios_cursados(usuario: dict) -> int:
    return max((usuario["anio"] or 1) - 1, 0)


def materias_por_anio(carrera_id: int, hasta_anio: int = 99) -> list[dict]:
    """Materias de la carrera hasta ese año, agrupadas por año (dos cuatrimestres por año)."""
    anios: dict[int, dict] = {}
    for materia in db.query(
        "SELECT id, nombre, cuatrimestre FROM materias WHERE carrera_id = :c AND activa = 1"
        " AND cuatrimestre <= :hasta ORDER BY cuatrimestre, nombre",
        c=carrera_id,
        hasta=hasta_anio * 2,
    ):
        anio = ((materia["cuatrimestre"] or 1) + 1) // 2
        anios.setdefault(anio, {"anio": anio, "materias": []})["materias"].append(materia)
    return list(anios.values())


def materias_con_catedra(usuario: dict) -> list[dict]:
    """Todas las materias que ya cursó en su carrera, si tiene el rol de cátedra."""
    if not usuario["catedra"] or not usuario["carrera_id"]:
        return []
    anios = materias_por_anio(usuario["carrera_id"], anios_cursados(usuario))
    return [m for anio in anios for m in anio["materias"]]


def cambiar_catedra(usuario_id: int, nombrar: bool) -> None:
    """El rol de cátedra lo da sólo el admin y vale en todo lo que el estudiante ya cursó (RN-03)."""
    with db.transaccion():
        if not db.bloquear_fila("usuarios", usuario_id):
            raise ErrorUsuario("El usuario no existe.")
        usuario = obtener_usuario(usuario_id)
        if bool(usuario["catedra"]) == nombrar:
            raise ErrorUsuario("Ya es estudiante de cátedra." if nombrar else "No es estudiante de cátedra.")
        if nombrar:
            if usuario["rol"] != "estudiante":
                raise ErrorUsuario("Sólo los estudiantes pueden ser de cátedra.")
            if not usuario["carrera_id"]:
                raise ErrorUsuario("El estudiante todavía no eligió su carrera.")
            if not anios_cursados(usuario):
                raise ErrorUsuario("Cursa el primer año: todavía no terminó ninguna materia.")
        db.execute("UPDATE usuarios SET catedra = :c WHERE id = :id", c=int(nombrar), id=usuario_id)
        if nombrar:
            notificar(
                usuario_id,
                "catedra",
                f"Ahora sos estudiante de cátedra de las materias que ya cursaste en {usuario['carrera_nombre']}.",
            )


_CONTEOS = {
    "reservas": "SELECT count(*) AS n FROM reservas WHERE usuario_id = :u AND estado = 'confirmada'",
    "actividades": "SELECT count(*) AS n FROM actividades WHERE creador_id = :u",
    "inscripciones": "SELECT count(*) AS n FROM inscripciones WHERE usuario_id = :u",
    "preguntas": "SELECT count(*) AS n FROM preguntas WHERE autor_id = :u",
    "respuestas": "SELECT count(*) AS n FROM respuestas WHERE autor_id = :u",
    "publicaciones": "SELECT count(*) AS n FROM publicaciones WHERE autor_id = :u",
    "reportes": "SELECT count(*) AS n FROM reportes WHERE tipo_objeto = 'usuario' AND objeto_id = :u",
}


def resumen_actividad(usuario_id: int) -> dict:
    resumen = {clave: db.query_one(sql, u=usuario_id)["n"] for clave, sql in _CONTEOS.items()}
    resumen["actividades_rechazadas"] = db.query_one(
        "SELECT count(*) AS n FROM actividades WHERE creador_id = :u AND estado = 'rechazada'", u=usuario_id
    )["n"]
    return resumen
