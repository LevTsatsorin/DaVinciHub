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
LIMITE_RESOLUCION = 500


class ErrorReporte(ValueError):
    pass


def ya_reporto(autor_id: int, tipo_objeto: str, objeto_id: int) -> bool:
    return db.query_one(
        "SELECT 1 AS existe FROM reportes WHERE autor_id = :a AND tipo_objeto = :t AND objeto_id = :o",
        a=autor_id, t=tipo_objeto, o=objeto_id,
    ) is not None


def crear_reporte(autor_id: int, tipo_objeto: str, objeto_id: int, motivo: str) -> int:
    tipos_validos = ("publicacion", "usuario", "pregunta", "respuesta", "actividad")
    if tipo_objeto not in tipos_validos:
        raise ErrorReporte("Tipo de contenido a reportar inválido.")
    if tipo_objeto == "usuario" and objeto_id == autor_id:
        raise ErrorReporte("No podés reportarte a vos mismo.")
    if ya_reporto(autor_id, tipo_objeto, objeto_id):
        if tipo_objeto == "usuario":
            raise ErrorReporte("Ya reportaste a este usuario.")
        raise ErrorReporte("Ya reportaste este contenido.")
    if not motivo or motivo not in MOTIVOS:
        raise ErrorReporte("Elegí un motivo válido.")
    fila = db.query_one(
        "INSERT INTO reportes (autor_id, tipo_objeto, objeto_id, motivo, creado)"
        " VALUES (:a, :t, :o, :m, :c) RETURNING id",
        a=autor_id, t=tipo_objeto, o=objeto_id, m=motivo, c=ahora(),
    )
    return fila["id"]


def enriquecer_reporte(r: dict) -> dict:
    tipo = r.get("tipo_objeto")
    oid = r.get("objeto_id")
    titulo = None
    enlace = None
    dueno_id = None
    dueno_nombre = None
    esta_oculto = False

    if tipo == "publicacion":
        pub = db.query_one(
            "SELECT p.titulo, p.autor_id, p.oculto, u.nombre, u.apellido"
            " FROM publicaciones p JOIN usuarios u ON u.id = p.autor_id WHERE p.id = :id",
            id=oid,
        )
        if pub:
            titulo = pub["titulo"]
            dueno_id = pub["autor_id"]
            dueno_nombre = f"{pub['nombre']} {pub['apellido']}"
            esta_oculto = bool(pub["oculto"])
            enlace = f"/objetos/{oid}"
    elif tipo == "pregunta":
        preg = db.query_one(
            "SELECT p.titulo, p.autor_id, p.oculto, u.nombre, u.apellido"
            " FROM preguntas p JOIN usuarios u ON u.id = p.autor_id WHERE p.id = :id",
            id=oid,
        )
        if preg:
            titulo = preg["titulo"]
            dueno_id = preg["autor_id"]
            dueno_nombre = f"{preg['nombre']} {preg['apellido']}"
            esta_oculto = bool(preg["oculto"])
            enlace = f"/foro/{oid}"
    elif tipo == "respuesta":
        resp = db.query_one(
            "SELECT r.cuerpo, r.pregunta_id, r.autor_id, r.oculto, u.nombre, u.apellido"
            " FROM respuestas r JOIN usuarios u ON u.id = r.autor_id WHERE r.id = :id",
            id=oid,
        )
        if resp:
            titulo = resp["cuerpo"][:100] + ("..." if len(resp["cuerpo"]) > 100 else "")
            dueno_id = resp["autor_id"]
            dueno_nombre = f"{resp['nombre']} {resp['apellido']}"
            esta_oculto = bool(resp["oculto"])
            enlace = f"/foro/{resp['pregunta_id']}#respuesta-{oid}"
    elif tipo == "actividad":
        act = db.query_one(
            "SELECT a.nombre, a.creador_id, a.oculto, u.nombre AS unombre, u.apellido AS uapellido"
            " FROM actividades a JOIN usuarios u ON u.id = a.creador_id WHERE a.id = :id",
            id=oid,
        )
        if act:
            titulo = act["nombre"]
            dueno_id = act["creador_id"]
            dueno_nombre = f"{act['unombre']} {act['uapellido']}"
            esta_oculto = bool(act["oculto"])
            enlace = f"/actividades/{oid}"
    elif tipo == "usuario":
        usu = db.query_one(
            "SELECT u.id, u.nombre, u.apellido, u.bloqueado FROM usuarios u WHERE u.id = :id",
            id=oid,
        )
        if usu:
            titulo = f"{usu['nombre']} {usu['apellido']}"
            dueno_id = usu["id"]
            dueno_nombre = titulo
            esta_oculto = bool(usu["bloqueado"])
            enlace = f"/estudiantes/{oid}"

    r["contenido_titulo"] = titulo
    r["contenido_enlace"] = enlace
    r["dueno_id"] = dueno_id
    r["dueno_nombre"] = dueno_nombre
    r["contenido_oculto"] = esta_oculto
    return r

def listar_reportes(estado: str = "pendiente") -> list[dict]:
    condicion = "WHERE r.estado = :estado" if estado in ("pendiente", "resuelto") else ""
    filas = db.query(
        "SELECT r.*, u.nombre AS autor_nombre, u.apellido AS autor_apellido,"
        " a.nombre AS resuelto_nombre, a.apellido AS resuelto_apellido"
        " FROM reportes r"
        " JOIN usuarios u ON u.id = r.autor_id"
        " LEFT JOIN usuarios a ON a.id = r.resuelto_por"
        f" {condicion} ORDER BY r.creado DESC, r.id DESC",
        estado=estado,
    )
    return [enriquecer_reporte(f) for f in filas]


def contar_pendientes() -> int:
    return db.query_one("SELECT count(*) AS n FROM reportes WHERE estado = 'pendiente'")["n"]


def obtener_reporte(reporte_id: int) -> dict | None:
    return db.query_one(
        "SELECT r.*, u.nombre AS autor_nombre, u.apellido AS autor_apellido,"
        " a.nombre AS resuelto_nombre, a.apellido AS resuelto_apellido"
        " FROM reportes r"
        " JOIN usuarios u ON u.id = r.autor_id"
        " LEFT JOIN usuarios a ON a.id = r.resuelto_por"
        " WHERE r.id = :id",
        id=reporte_id,
    )


def resolver_reporte(reporte_id: int, admin_id: int, accion: str, resolucion: str) -> None:
    """
    accion: 'descartar' | 'ocultar'
    - descartar: marca resuelto, sin ocultar nada
    - ocultar: marca resuelto + pone oculto=1 en el contenido
    """
    resolucion = (resolucion or "").strip()
    if not resolucion:
        raise ErrorReporte("Escribí el motivo de la resolución.")
    if len(resolucion) > LIMITE_RESOLUCION:
        raise ErrorReporte(f"El motivo admite hasta {LIMITE_RESOLUCION} caracteres.")
    if accion not in ("descartar", "ocultar", "bloquear"):
        raise ErrorReporte("Acción inválida.")

    with db.transaccion():
        reporte = db.query_one("SELECT * FROM reportes WHERE id = :id", id=reporte_id)
        if reporte is None:
            raise ErrorReporte("Reporte no encontrado.")
        if reporte["estado"] == "resuelto":
            raise ErrorReporte("Este reporte ya fue resuelto.")

        if accion == "ocultar":
            tablas = {
                "publicacion": "publicaciones",
                "pregunta": "preguntas",
                "respuesta": "respuestas",
                "actividad": "actividades",
            }
            tabla = tablas.get(reporte["tipo_objeto"])
            if tabla:
                db.execute(f"UPDATE {tabla} SET oculto = 1 WHERE id = :id", id=reporte["objeto_id"])

        db.execute(
            "UPDATE reportes SET estado = 'resuelto', resolucion = :res, resuelto_por = :admin"
            " WHERE id = :id",
            res=resolucion, admin=admin_id, id=reporte_id,
        )

        # Notificar al que reportó
        notificar(
            reporte["autor_id"],
            "reporte_resuelto",
            "Tu reporte fue revisado y resuelto por el equipo de Da Vinci Hub.",
        )


def restaurar_contenido(tipo_objeto: str, objeto_id: int) -> None:
    tablas = {
        "publicacion": "publicaciones",
        "pregunta": "preguntas",
        "respuesta": "respuestas",
        "actividad": "actividades",
    }
    tabla = tablas.get(tipo_objeto)
    if not tabla:
        raise ErrorReporte("Tipo de contenido inválido.")
    db.execute(f"UPDATE {tabla} SET oculto = 0 WHERE id = :id", id=objeto_id)

