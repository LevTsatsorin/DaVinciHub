from io import BytesIO

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from davincihub import db, seguridad, validacion
from davincihub.notificaciones import notificar
from davincihub.usuarios import datos as usuarios_datos
from davincihub.utiles import ahora

bp = Blueprint("perfil", __name__, url_prefix="/estudiantes")
MAX_FOTO_BYTES = 3 * 1024 * 1024
TEMAS_CHAT = {"davinci": "Da Vinci", "menta": "Menta", "violeta": "Violeta", "ambar": "Ámbar", "noche": "Noche"}


def _tipo_foto(contenido: bytes) -> str | None:
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if contenido.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if contenido.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp"
    return None


def _estudiante_publico(usuario_id: int) -> dict | None:
    return db.query_one(
        "SELECT u.id, u.nombre, u.apellido, u.carrera_id, u.anio, u.comision, u.catedra,"
        " c.nombre AS carrera, CASE WHEN f.usuario_id IS NULL THEN 0 ELSE 1 END AS tiene_foto"
        " FROM usuarios u LEFT JOIN carreras c ON c.id = u.carrera_id"
        " LEFT JOIN fotos_perfil f ON f.usuario_id = u.id"
        " WHERE u.id = :id AND u.rol = 'estudiante' AND u.bloqueado = 0",
        id=usuario_id,
    )


@bp.get("/<int:usuario_id>/foto")
def foto(usuario_id: int):
    if _estudiante_publico(usuario_id) is None:
        abort(404)
    imagen = db.query_one(
        "SELECT tipo, contenido FROM fotos_perfil WHERE usuario_id = :id", id=usuario_id
    )
    if imagen is None:
        abort(404)
    respuesta = send_file(
        BytesIO(bytes(imagen["contenido"])),
        mimetype=imagen["tipo"],
        download_name=f"perfil-{usuario_id}",
        max_age=0,
    )
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    return respuesta


def _estado_conexion(otro_id: int) -> dict | None:
    return db.query_one(
        "SELECT solicitante_id, receptor_id, estado FROM conexiones"
        " WHERE (solicitante_id = :yo AND receptor_id = :otro)"
        " OR (solicitante_id = :otro AND receptor_id = :yo)"
        " ORDER BY CASE WHEN estado = 'aceptada' THEN 0 ELSE 1 END LIMIT 1",
        yo=g.usuario["id"],
        otro=otro_id,
    )


@bp.get("/<int:usuario_id>")
def ver(usuario_id: int):
    estudiante = _estudiante_publico(usuario_id)
    if estudiante is None:
        abort(404)

    materias = usuarios_datos.materias_con_catedra(estudiante)
    reputacion = db.query_one(
        "SELECT AVG(valor) AS promedio, COUNT(*) AS cantidad FROM valoraciones_operaciones"
        " WHERE receptor_id = :id",
        id=usuario_id,
    )
    intercambios = db.query_one(
        "SELECT"
        " (SELECT COUNT(*) FROM intercambios i JOIN publicaciones p ON p.id = i.publicacion_id"
        "  WHERE i.estado = 'completado' AND (i.solicitante_id = :id OR p.autor_id = :id))"
        " + (SELECT COUNT(*) FROM ventas v JOIN publicaciones p ON p.id = v.publicacion_id"
        "  WHERE v.estado = 'completada' AND (v.comprador_id = :id OR p.autor_id = :id))"
        " + (SELECT COUNT(*) FROM prestamos pr JOIN publicaciones p ON p.id = pr.publicacion_id"
        "  WHERE pr.estado = 'devuelto' AND (pr.solicitante_id = :id OR p.autor_id = :id))"
        " AS total",
        id=usuario_id,
    )
    respuestas_utiles = db.query_one(
        "SELECT COUNT(*) AS total FROM respuestas"
        " WHERE autor_id = :id AND aceptada = 1",
        id=usuario_id,
    )
    actividades = db.query(
        "SELECT a.id, a.nombre, a.inicio, a.ubicacion FROM inscripciones i"
        " JOIN actividades a ON a.id = i.actividad_id"
        " WHERE i.usuario_id = :id AND a.estado = 'aprobada'"
        " ORDER BY a.inicio DESC LIMIT 5",
        id=usuario_id,
    )
    actividades_total = db.query_one(
        "SELECT COUNT(*) AS total FROM inscripciones i"
        " JOIN actividades a ON a.id = i.actividad_id"
        " WHERE i.usuario_id = :id AND a.estado = 'aprobada'",
        id=usuario_id,
    )["total"]
    conexion = _estado_conexion(usuario_id) if g.usuario and g.usuario["id"] != usuario_id else None
    return render_template(
        "perfil/perfil.html",
        estudiante=estudiante,
        materias=materias,
        reputacion=reputacion,
        intercambios=intercambios["total"],
        respuestas_utiles=respuestas_utiles["total"],
        actividades=actividades,
        actividades_total=actividades_total,
        conexion=conexion,
    )


@bp.route("/<int:usuario_id>/editar", methods=("GET", "POST"))
@seguridad.requiere_login
def editar(usuario_id: int):
    if g.usuario["id"] != usuario_id:
        abort(403)
    estudiante = db.query_one(
        "SELECT u.id, u.nombre, u.apellido, u.email, u.carrera_id, u.anio, u.comision, u.catedra,"
        " CASE WHEN f.usuario_id IS NULL THEN 0 ELSE 1 END AS tiene_foto"
        " FROM usuarios u LEFT JOIN fotos_perfil f ON f.usuario_id = u.id"
        " WHERE u.id = :id AND u.rol = 'estudiante'",
        id=usuario_id,
    )
    if estudiante is None:
        abort(404)

    errores = {}
    if request.method == "POST":
        datos = request.form
        errores = validacion.validar_datos_estudiante(datos)
        for campo in ("nombre", "apellido"):
            if not (datos.get(campo) or "").strip():
                errores[campo] = "Campo obligatorio."
        carrera_id = (datos.get("carrera_id") or "").strip()
        if not errores and not db.query_one(
            "SELECT id FROM carreras WHERE id = :id AND activa = 1", id=int(carrera_id)
        ):
            errores["carrera_id"] = "Elegí una carrera válida."
        archivo_foto = request.files.get("foto")
        contenido_foto = archivo_foto.read(MAX_FOTO_BYTES + 1) if archivo_foto and archivo_foto.filename else None
        tipo_foto = _tipo_foto(contenido_foto) if contenido_foto else None
        if contenido_foto and len(contenido_foto) > MAX_FOTO_BYTES:
            errores["foto"] = "La imagen supera el tamaño máximo permitido de 3 MB."
        elif contenido_foto and tipo_foto is None:
            errores["foto"] = "Usá una imagen PNG, JPG, GIF o WebP válida."
        if not errores:
            with db.transaccion():
                db.execute(
                    "UPDATE usuarios SET nombre = :nombre, apellido = :apellido,"
                    " carrera_id = :carrera, anio = :anio, comision = :comision,"
                    " catedra = CASE WHEN carrera_id = :carrera THEN catedra ELSE 0 END WHERE id = :id",
                    nombre=datos["nombre"].strip(),
                    apellido=datos["apellido"].strip(),
                    carrera=int(carrera_id),
                    anio=int(datos["anio"]),
                    comision=datos["comision"].strip(),
                    id=usuario_id,
                )
                if contenido_foto:
                    db.execute("DELETE FROM fotos_perfil WHERE usuario_id = :id", id=usuario_id)
                    db.execute(
                        "INSERT INTO fotos_perfil (usuario_id, tipo, contenido, actualizado)"
                        " VALUES (:id, :tipo, :contenido, :actualizado)",
                        id=usuario_id,
                        tipo=tipo_foto,
                        contenido=contenido_foto,
                        actualizado=ahora(),
                    )
            flash("Tu perfil quedó actualizado.")
            return redirect(url_for("perfil.ver", usuario_id=usuario_id))
    else:
        datos = estudiante

    carreras = db.query("SELECT id, nombre FROM carreras WHERE activa = 1 ORDER BY nombre")
    return render_template(
        "perfil/editar.html",
        estudiante=estudiante,
        datos=datos,
        errores=errores,
        carreras=carreras,
    )


@bp.post("/<int:usuario_id>/conexiones")
@seguridad.requiere_login
def solicitar_conexion(usuario_id: int):
    if g.usuario["rol"] != "estudiante":
        abort(403)
    if usuario_id == g.usuario["id"] or _estudiante_publico(usuario_id) is None:
        abort(404)
    if _estado_conexion(usuario_id):
        flash("Ya existe una solicitud o conexión entre ustedes.")
    else:
        try:
            db.execute(
                "INSERT INTO conexiones (solicitante_id, receptor_id, estado, creado)"
                " VALUES (:solicitante, :receptor, 'pendiente', :creado)",
                solicitante=g.usuario["id"],
                receptor=usuario_id,
                creado=ahora(),
            )
        except db.ErrorIntegridad:
            flash("Ya existe una solicitud o conexión entre ustedes.")
        else:
            notificar(
                usuario_id,
                "conexion",
                f"{g.usuario['nombre']} {g.usuario['apellido']} quiere conectar con vos.",
                url_for("perfil.conexiones", usuario_id=usuario_id),
            )
            flash("Solicitud de conexión enviada.")
    return redirect(url_for("perfil.ver", usuario_id=usuario_id))


def _resolver_solicitud(usuario_id: int, solicitante_id: int, estado: str):
    if g.usuario["id"] != usuario_id:
        abort(403)
    solicitud = db.query_one(
        "SELECT id FROM conexiones WHERE solicitante_id = :solicitante"
        " AND receptor_id = :receptor AND estado = 'pendiente'",
        solicitante=solicitante_id,
        receptor=usuario_id,
    )
    if solicitud is None:
        abort(404)
    db.execute(
        "UPDATE conexiones SET estado = :estado WHERE id = :id AND estado = 'pendiente'",
        estado=estado,
        id=solicitud["id"],
    )
    if estado == "aceptada":
        notificar(
            solicitante_id,
            "conexion",
            f"{g.usuario['nombre']} {g.usuario['apellido']} aceptó tu solicitud de conexión.",
            url_for("perfil.ver", usuario_id=usuario_id),
        )
    flash("Conexión aceptada." if estado == "aceptada" else "Solicitud rechazada.")
    return redirect(url_for("perfil.conexiones", usuario_id=usuario_id))


@bp.post("/<int:usuario_id>/conexiones/<int:solicitante_id>/aceptar")
@seguridad.requiere_login
def aceptar_conexion(usuario_id: int, solicitante_id: int):
    return _resolver_solicitud(usuario_id, solicitante_id, "aceptada")


@bp.post("/<int:usuario_id>/conexiones/<int:solicitante_id>/rechazar")
@seguridad.requiere_login
def rechazar_conexion(usuario_id: int, solicitante_id: int):
    return _resolver_solicitud(usuario_id, solicitante_id, "rechazada")


@bp.get("/<int:usuario_id>/conexiones")
@seguridad.requiere_login
def conexiones(usuario_id: int):
    if g.usuario["id"] != usuario_id:
        abort(403)
    solicitudes_recibidas = db.query(
        "SELECT u.id, u.nombre, u.apellido, c.nombre AS carrera,"
        " CASE WHEN f.usuario_id IS NULL THEN 0 ELSE 1 END AS tiene_foto"
        " FROM conexiones x JOIN usuarios u ON u.id = x.solicitante_id"
        " LEFT JOIN carreras c ON c.id = u.carrera_id"
        " LEFT JOIN fotos_perfil f ON f.usuario_id = u.id"
        " WHERE x.receptor_id = :id AND x.estado = 'pendiente'"
        " AND u.rol = 'estudiante' AND u.bloqueado = 0 ORDER BY x.creado, u.nombre",
        id=usuario_id,
    )
    enviadas = db.query(
        "SELECT u.id, u.nombre, u.apellido, c.nombre AS carrera,"
        " CASE WHEN f.usuario_id IS NULL THEN 0 ELSE 1 END AS tiene_foto"
        " FROM conexiones x JOIN usuarios u ON u.id = x.receptor_id"
        " LEFT JOIN carreras c ON c.id = u.carrera_id"
        " LEFT JOIN fotos_perfil f ON f.usuario_id = u.id"
        " WHERE x.solicitante_id = :id AND x.estado = 'pendiente'"
        " AND u.rol = 'estudiante' AND u.bloqueado = 0 ORDER BY x.creado DESC",
        id=usuario_id,
    )
    aceptadas = db.query(
        "SELECT u.id, u.nombre, u.apellido, c.nombre AS carrera,"
        " CASE WHEN f.usuario_id IS NULL THEN 0 ELSE 1 END AS tiene_foto"
        " FROM conexiones x JOIN usuarios u ON u.id = CASE WHEN x.solicitante_id = :id"
        " THEN x.receptor_id ELSE x.solicitante_id END"
        " LEFT JOIN carreras c ON c.id = u.carrera_id"
        " LEFT JOIN fotos_perfil f ON f.usuario_id = u.id"
        " WHERE (x.solicitante_id = :id OR x.receptor_id = :id)"
        " AND x.estado = 'aceptada' AND u.rol = 'estudiante' AND u.bloqueado = 0"
        " ORDER BY u.nombre, u.apellido",
        id=usuario_id,
    )
    return render_template(
        "perfil/conexiones.html",
        estudiante=g.usuario,
        solicitudes_recibidas=solicitudes_recibidas,
        enviadas=enviadas,
        conexiones=aceptadas,
    )


@bp.get("/chats")
@seguridad.requiere_login
def chats():
    if g.usuario["rol"] != "estudiante":
        abort(403)
    conversaciones = db.query(
        "SELECT u.id, u.nombre, u.apellido,"
        " CASE WHEN f.usuario_id IS NULL THEN 0 ELSE 1 END AS tiene_foto,"
        " m.cuerpo AS ultimo_mensaje, m.creado AS ultimo_creado,"
        " m.emisor_id AS ultimo_emisor_id,"
        " (SELECT count(*) FROM mensajes sin_leer"
        "  WHERE sin_leer.emisor_id = u.id AND sin_leer.receptor_id = :yo"
        "  AND sin_leer.leido = 0) AS sin_leer"
        " FROM (SELECT DISTINCT CASE WHEN emisor_id = :yo THEN receptor_id"
        "  ELSE emisor_id END AS otro_id FROM mensajes"
        "  WHERE emisor_id = :yo OR receptor_id = :yo) pares"
        " JOIN usuarios u ON u.id = pares.otro_id AND u.rol = 'estudiante' AND u.bloqueado = 0"
        " LEFT JOIN fotos_perfil f ON f.usuario_id = u.id"
        " JOIN mensajes m ON m.id = (SELECT ultimo.id FROM mensajes ultimo"
        "  WHERE (ultimo.emisor_id = :yo AND ultimo.receptor_id = u.id)"
        "  OR (ultimo.emisor_id = u.id AND ultimo.receptor_id = :yo)"
        "  ORDER BY ultimo.creado DESC, ultimo.id DESC LIMIT 1)"
        " ORDER BY m.creado DESC, m.id DESC",
        yo=g.usuario["id"],
    )
    return render_template("perfil/chats.html", conversaciones=conversaciones)


@bp.route("/<int:usuario_id>/chat", methods=("GET", "POST"))
@seguridad.requiere_login
def chat(usuario_id: int):
    if g.usuario["rol"] != "estudiante":
        abort(403)
    if usuario_id == g.usuario["id"] or _estudiante_publico(usuario_id) is None:
        abort(404)
    error = None
    cuerpo = (request.form.get("cuerpo") or "").replace("\r\n", "\n").strip()
    if request.method == "POST":
        if not cuerpo or len(cuerpo) > 2000:
            error = "El mensaje debe tener entre 1 y 2000 caracteres."
        else:
            enlace = url_for("perfil.chat", usuario_id=g.usuario["id"])
            with db.transaccion():
                db.execute(
                    "INSERT INTO mensajes (emisor_id, receptor_id, cuerpo, creado)"
                    " VALUES (:emisor, :receptor, :cuerpo, :creado)",
                    emisor=g.usuario["id"],
                    receptor=usuario_id,
                    cuerpo=cuerpo,
                    creado=ahora(),
                )
                if not db.query_one(
                    "SELECT id FROM notificaciones WHERE usuario_id = :u AND enlace = :e AND leida = 0",
                    u=usuario_id,
                    e=enlace,
                ):
                    notificar(
                        usuario_id,
                        "mensaje",
                        f"{g.usuario['nombre']} {g.usuario['apellido']} te escribió un mensaje.",
                        enlace,
                    )
            return redirect(url_for("perfil.chat", usuario_id=usuario_id))
    with db.transaccion():
        db.execute(
            "UPDATE mensajes SET leido = 1 WHERE receptor_id = :yo AND emisor_id = :otro AND leido = 0",
            yo=g.usuario["id"],
            otro=usuario_id,
        )
        db.execute(
            "UPDATE notificaciones SET leida = 1 WHERE usuario_id = :yo AND enlace = :e AND leida = 0",
            yo=g.usuario["id"],
            e=url_for("perfil.chat", usuario_id=usuario_id),
        )
    mensajes = db.query(
        "SELECT m.emisor_id, m.receptor_id, m.cuerpo, m.creado,"
        " emisor.nombre AS emisor_nombre, emisor.apellido AS emisor_apellido"
        " FROM mensajes m JOIN usuarios emisor ON emisor.id = m.emisor_id"
        " WHERE (m.emisor_id = :yo AND m.receptor_id = :otro)"
        " OR (m.emisor_id = :otro AND m.receptor_id = :yo) ORDER BY m.creado, m.id",
        yo=g.usuario["id"],
        otro=usuario_id,
    )
    return render_template(
        "perfil/chat.html",
        temas=TEMAS_CHAT,
        estudiante=_estudiante_publico(usuario_id),
        mensajes=mensajes,
        error=error,
        cuerpo=cuerpo,
    )


@bp.post("/<int:usuario_id>/chat/tema")
@seguridad.requiere_login
def tema_chat(usuario_id: int):
    if g.usuario["rol"] != "estudiante":
        abort(403)
    tema = request.form.get("tema")
    if tema not in TEMAS_CHAT:
        abort(400)
    db.execute("UPDATE usuarios SET chat_tema = :tema WHERE id = :id", tema=tema, id=g.usuario["id"])
    return redirect(url_for("perfil.chat", usuario_id=usuario_id))


@bp.post("/<int:usuario_id>/contrasena")
@seguridad.requiere_login
def cambiar_contrasena(usuario_id: int):
    if g.usuario["id"] != usuario_id:
        abort(403)
    actual = request.form.get("password_actual") or ""
    nueva = request.form.get("password_nueva") or ""
    confirmar = request.form.get("confirmar") or ""
    if not check_password_hash(g.usuario["password_hash"], actual):
        flash("La contraseña actual no es correcta.")
    elif len(nueva) < 8:
        flash("La nueva contraseña necesita al menos 8 caracteres.")
    elif nueva != confirmar:
        flash("Las contraseñas nuevas no coinciden.")
    else:
        db.execute(
            "UPDATE usuarios SET password_hash = :hash WHERE id = :id",
            hash=generate_password_hash(nueva),
            id=usuario_id,
        )
        flash("Contraseña actualizada.")
    return redirect(url_for("perfil.editar", usuario_id=usuario_id))
