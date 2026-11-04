from davincihub import db
from davincihub.notificaciones import notificar
from davincihub.utiles import ahora

MOTIVOS = [
    "Contenido inapropiado u ofensivo",
    "Acoso o discriminación",
    "Spam o publicidad no permitida",
    "Información falsa o engañosa",
    "Otro",
]
TIPOS = {
    "publicacion": "Publicación",
    "pregunta": "Pregunta",
    "respuesta": "Respuesta",
    "actividad": "Actividad",
    "usuario": "Perfil",
}
TABLAS_OCULTABLES = {
    "publicacion": "publicaciones",
    "pregunta": "preguntas",
    "respuesta": "respuestas",
    "actividad": "actividades",
}
_DUENO = {
    "publicacion": ("publicaciones", "autor_id"),
    "pregunta": ("preguntas", "autor_id"),
    "respuesta": ("respuestas", "autor_id"),
    "actividad": ("actividades", "creador_id"),
    "usuario": ("usuarios", "id"),
}
ACCIONES = ("descartar", "ocultar", "bloquear")
AVISOS = {
    "descartar": "Revisamos tu reporte y no encontramos una falta a las normas del Hub.",
    "ocultar": "Revisamos tu reporte: el contenido ya no es visible para la comunidad.",
    "bloquear": "Revisamos tu reporte y lo derivamos a la revisión de la cuenta.",
}
LIMITE_RESOLUCION = 500


class ErrorReporte(ValueError):
    pass


def dueno_del_objeto(tipo_objeto: str, objeto_id: int) -> int | None:
    if tipo_objeto not in _DUENO:
        return None
    tabla, columna = _DUENO[tipo_objeto]
    fila = db.query_one(f"SELECT {columna} AS uid FROM {tabla} WHERE id = :id", id=objeto_id)
    return fila["uid"] if fila else None


def ya_reporto(autor_id: int, tipo_objeto: str, objeto_id: int) -> bool:
    return db.query_one(
        "SELECT 1 AS existe FROM reportes WHERE autor_id = :a AND tipo_objeto = :t AND objeto_id = :o",
        a=autor_id, t=tipo_objeto, o=objeto_id,
    ) is not None


def crear_reporte(autor_id: int, tipo_objeto: str, objeto_id: int, motivo: str) -> int:
    if tipo_objeto not in TIPOS:
        raise ErrorReporte("Tipo de contenido a reportar inválido.")
    dueno = dueno_del_objeto(tipo_objeto, objeto_id)
    if dueno is None:
        raise ErrorReporte("El contenido que querés reportar ya no existe.")
    if dueno == autor_id:
        raise ErrorReporte("No podés reportarte a vos mismo." if tipo_objeto == "usuario"
                           else "No podés reportar tu propio contenido.")
    if motivo not in MOTIVOS:
        raise ErrorReporte("Elegí un motivo válido.")
    repetido = ErrorReporte("Ya reportaste a este usuario." if tipo_objeto == "usuario"
                            else "Ya reportaste este contenido.")
    if ya_reporto(autor_id, tipo_objeto, objeto_id):
        raise repetido
    try:
        fila = db.query_one(
            "INSERT INTO reportes (autor_id, tipo_objeto, objeto_id, motivo, creado)"
            " VALUES (:a, :t, :o, :m, :c) RETURNING id",
            a=autor_id, t=tipo_objeto, o=objeto_id, m=motivo, c=ahora(),
        )
    except db.ErrorIntegridad:
        raise repetido from None
    return fila["id"]


def enriquecer_reporte(r: dict) -> dict:
    tipo, oid = r["tipo_objeto"], r["objeto_id"]
    titulo = enlace = dueno_id = dueno_nombre = None
    oculto = False
    if tipo in ("publicacion", "pregunta", "actividad"):
        tabla, campo, autor = {
            "publicacion": ("publicaciones", "titulo", "autor_id"),
            "pregunta": ("preguntas", "titulo", "autor_id"),
            "actividad": ("actividades", "nombre", "creador_id"),
        }[tipo]
        fila = db.query_one(
            f"SELECT x.{campo} AS titulo, x.{autor} AS dueno, x.oculto, u.nombre, u.apellido"
            f" FROM {tabla} x JOIN usuarios u ON u.id = x.{autor} WHERE x.id = :id",
            id=oid,
        )
        if fila:
            titulo, dueno_id, oculto = fila["titulo"], fila["dueno"], bool(fila["oculto"])
            dueno_nombre = f"{fila['nombre']} {fila['apellido']}"
            enlace = {"publicacion": f"/objetos/{oid}", "pregunta": f"/foro/preguntas/{oid}",
                      "actividad": f"/actividades/{oid}"}[tipo]
    elif tipo == "respuesta":
        fila = db.query_one(
            "SELECT r.cuerpo, r.pregunta_id, r.autor_id, r.oculto, u.nombre, u.apellido"
            " FROM respuestas r JOIN usuarios u ON u.id = r.autor_id WHERE r.id = :id",
            id=oid,
        )
        if fila:
            titulo = fila["cuerpo"][:140] + ("…" if len(fila["cuerpo"]) > 140 else "")
            dueno_id, oculto = fila["autor_id"], bool(fila["oculto"])
            dueno_nombre = f"{fila['nombre']} {fila['apellido']}"
            enlace = f"/foro/preguntas/{fila['pregunta_id']}#respuesta-{oid}"
    elif tipo == "usuario":
        fila = db.query_one("SELECT id, nombre, apellido, bloqueado FROM usuarios WHERE id = :id", id=oid)
        if fila:
            titulo = dueno_nombre = f"{fila['nombre']} {fila['apellido']}"
            dueno_id, oculto = fila["id"], bool(fila["bloqueado"])
            enlace = f"/estudiantes/{oid}"
    r.update(contenido_titulo=titulo, contenido_enlace=enlace, dueno_id=dueno_id,
             dueno_nombre=dueno_nombre, contenido_oculto=oculto, tipo_nombre=TIPOS.get(tipo, tipo))
    return r


_SELECT = (
    "SELECT r.*, u.nombre AS autor_nombre, u.apellido AS autor_apellido,"
    " a.nombre AS resuelto_nombre, a.apellido AS resuelto_apellido,"
    " (SELECT COUNT(*) FROM reportes o WHERE o.tipo_objeto = r.tipo_objeto AND o.objeto_id = r.objeto_id"
    "  AND o.estado = 'pendiente') AS pendientes_mismo"
    " FROM reportes r JOIN usuarios u ON u.id = r.autor_id LEFT JOIN usuarios a ON a.id = r.resuelto_por"
)


def listar_reportes(estado: str = "pendiente") -> list[dict]:
    orden = "r.creado ASC, r.id ASC" if estado == "pendiente" else "r.resuelto DESC, r.id DESC"
    filas = db.query(_SELECT + f" WHERE r.estado = :estado ORDER BY {orden}", estado=estado)
    return [enriquecer_reporte(f) for f in filas]


def agrupar(reportes: list[dict]) -> list[dict]:
    grupos: dict[tuple, dict] = {}
    for r in reportes:
        clave = (r["tipo_objeto"], r["objeto_id"]) if r["estado"] == "pendiente" else (r["id"],)
        grupo = grupos.setdefault(clave, {"principal": r, "reportes": []})
        grupo["reportes"].append(r)
    return list(grupos.values())


def contar_pendientes() -> int:
    return db.query_one("SELECT count(*) AS n FROM reportes WHERE estado = 'pendiente'")["n"]


def obtener_reporte(reporte_id: int) -> dict | None:
    return db.query_one(_SELECT + " WHERE r.id = :id", id=reporte_id)


def resolver_reporte(reporte_id: int, admin_id: int, accion: str, resolucion: str) -> dict:
    """Resuelve el reporte y, con la misma decisión, los demás pendientes sobre ese contenido."""
    resolucion = (resolucion or "").strip()
    if accion not in ACCIONES:
        raise ErrorReporte("Acción inválida.")
    if not resolucion:
        raise ErrorReporte("Escribí el motivo de la resolución.")
    if len(resolucion) > LIMITE_RESOLUCION:
        raise ErrorReporte(f"El motivo admite hasta {LIMITE_RESOLUCION} caracteres.")
    with db.transaccion():
        if not db.bloquear_fila("reportes", reporte_id):
            raise ErrorReporte("Reporte no encontrado.")
        reporte = db.query_one("SELECT * FROM reportes WHERE id = :id", id=reporte_id)
        if reporte["estado"] == "resuelto":
            raise ErrorReporte("Este reporte ya fue resuelto.")
        tabla = TABLAS_OCULTABLES.get(reporte["tipo_objeto"])
        if accion == "ocultar":
            if not tabla:
                raise ErrorReporte("Un perfil no se oculta: derivalo a bloqueo.")
            db.execute(f"UPDATE {tabla} SET oculto = 1 WHERE id = :id", id=reporte["objeto_id"])
        ids = [
            f["id"] for f in db.query(
                "SELECT id FROM reportes WHERE tipo_objeto = :t AND objeto_id = :o AND estado = 'pendiente'",
                t=reporte["tipo_objeto"], o=reporte["objeto_id"],
            )
        ]
        momento = ahora()
        for rid in ids:
            fila = db.query_one("SELECT autor_id FROM reportes WHERE id = :id", id=rid)
            db.execute(
                "UPDATE reportes SET estado = 'resuelto', accion = :accion, resolucion = :res,"
                " resuelto_por = :admin, resuelto = :momento WHERE id = :id",
                accion=accion, res=resolucion, admin=admin_id, momento=momento, id=rid,
            )
            notificar(fila["autor_id"], "reportes", AVISOS[accion])
    return {"resueltos": len(ids), "dueno_id": dueno_del_objeto(reporte["tipo_objeto"], reporte["objeto_id"])}


def restaurar_contenido(reporte_id: int, admin_id: int) -> None:
    with db.transaccion():
        reporte = db.query_one("SELECT * FROM reportes WHERE id = :id", id=reporte_id)
        tabla = TABLAS_OCULTABLES.get(reporte["tipo_objeto"]) if reporte else None
        if not tabla:
            raise ErrorReporte("Este reporte no tiene contenido para restaurar.")
        cambiadas = db.execute(f"UPDATE {tabla} SET oculto = 0 WHERE id = :id AND oculto = 1", id=reporte["objeto_id"])
        if cambiadas != 1:
            raise ErrorReporte("El contenido ya estaba visible.")
        db.execute(
            "UPDATE reportes SET accion = 'restaurar', resuelto_por = :admin, resuelto = :momento"
            " WHERE tipo_objeto = :t AND objeto_id = :o AND accion = 'ocultar'",
            admin=admin_id, momento=ahora(), t=reporte["tipo_objeto"], o=reporte["objeto_id"],
        )
