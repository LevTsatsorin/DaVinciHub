from datetime import UTC, datetime
from io import BytesIO

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from davincihub import db, seguridad, validacion

bp = Blueprint("perfil", __name__, url_prefix="/estudiantes")
MAX_FOTO_BYTES = 3 * 1024 * 1024


def _ahora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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
        "SELECT u.id, u.nombre, u.apellido, u.carrera_id, u.anio, u.comision,"
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


def _materias_validas(ids: list[str], carrera_id: str) -> list[int] | None:
    if any(not identificador.isdecimal() for identificador in ids):
        return None
    seleccionadas = list(dict.fromkeys(int(identificador) for identificador in ids))
    if not seleccionadas:
        return []
    parametros = {f"id{indice}": identificador for indice, identificador in enumerate(seleccionadas)}
    placeholders = ", ".join(f":id{indice}" for indice in range(len(seleccionadas)))
    parametros["carrera"] = int(carrera_id) if carrera_id.isdecimal() else -1
    filas = db.query(
        f"SELECT id FROM materias WHERE activa = 1 AND carrera_id = :carrera"
        f" AND id IN ({placeholders})",
        **parametros,
    )
    if len(filas) != len(seleccionadas):
        return None
    return seleccionadas


@bp.get("/<int:usuario_id>")
def ver(usuario_id: int):
    estudiante = _estudiante_publico(usuario_id)
    if estudiante is None:
        abort(404)

    materias = db.query(
        "SELECT m.nombre FROM catedras c JOIN materias m ON m.id = c.materia_id"
        " WHERE c.usuario_id = :id AND m.activa = 1 ORDER BY m.nombre",
        id=usuario_id,
    )
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
    conexiones = db.query(
        "SELECT u.id, u.nombre, u.apellido, c.nombre AS carrera FROM conexiones x"
        " JOIN usuarios u ON u.id = CASE WHEN x.solicitante_id = :id"
        " THEN x.receptor_id ELSE x.solicitante_id END"
        " LEFT JOIN carreras c ON c.id = u.carrera_id"
        " WHERE (x.solicitante_id = :id OR x.receptor_id = :id)"
        " AND x.estado = 'aceptada' AND u.bloqueado = 0 ORDER BY u.nombre, u.apellido",
        id=usuario_id,
    )
    solicitudes_recibidas = []
    if g.usuario and g.usuario["id"] == usuario_id:
        solicitudes_recibidas = db.query(
            "SELECT u.id, u.nombre, u.apellido, c.nombre AS carrera FROM conexiones x"
            " JOIN usuarios u ON u.id = x.solicitante_id"
            " LEFT JOIN carreras c ON c.id = u.carrera_id"
            " WHERE x.receptor_id = :id AND x.estado = 'pendiente' AND u.bloqueado = 0"
            " ORDER BY x.creado, u.nombre",
            id=usuario_id,
        )
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
        conexiones=conexiones,
        solicitudes_recibidas=solicitudes_recibidas,
    )


@bp.route("/<int:usuario_id>/editar", methods=("GET", "POST"))
@seguridad.requiere_login
def editar(usuario_id: int):
    if g.usuario["id"] != usuario_id:
        abort(403)
    estudiante = db.query_one(
        "SELECT u.id, u.nombre, u.apellido, u.email, u.carrera_id, u.anio, u.comision,"
        " CASE WHEN f.usuario_id IS NULL THEN 0 ELSE 1 END AS tiene_foto"
        " FROM usuarios u LEFT JOIN fotos_perfil f ON f.usuario_id = u.id"
        " WHERE u.id = :id AND u.rol = 'estudiante'",
        id=usuario_id,
    )
    if estudiante is None:
        abort(404)

    errores = {}
    seleccionadas = [
        str(fila["id"])
        for fila in db.query("SELECT materia_id AS id FROM catedras WHERE usuario_id = :id", id=usuario_id)
    ]
    if request.method == "POST":
        datos = request.form
        errores = validacion.validar_datos_estudiante(datos)
        for campo in ("nombre", "apellido", "email"):
            if not (datos.get(campo) or "").strip():
                errores[campo] = "Campo obligatorio."
        email = (datos.get("email") or "").strip().lower()
        if email and ("@" not in email or "." not in email.rsplit("@", 1)[-1]):
            errores.setdefault("email", "Email inválido.")
        if email and db.query_one(
            "SELECT id FROM usuarios WHERE email = :email AND id <> :id", email=email, id=usuario_id
        ):
            errores["email"] = "Ese email ya está registrado."
        carrera_id = (datos.get("carrera_id") or "").strip()
        if not errores and not db.query_one(
            "SELECT id FROM carreras WHERE id = :id AND activa = 1", id=int(carrera_id)
        ):
            errores["carrera_id"] = "Elegí una carrera válida."
        seleccionadas = request.form.getlist("materias_catedra")
        materias_validas = _materias_validas(seleccionadas, carrera_id)
        if materias_validas is None:
            errores["materias_catedra"] = "Elegí materias válidas."
        archivo_foto = request.files.get("foto")
        contenido_foto = archivo_foto.read(MAX_FOTO_BYTES + 1) if archivo_foto and archivo_foto.filename else None
        tipo_foto = _tipo_foto(contenido_foto) if contenido_foto else None
        if contenido_foto and len(contenido_foto) > MAX_FOTO_BYTES:
            errores["foto"] = "La imagen supera el tamaño máximo permitido de 3 MB."
        elif contenido_foto and tipo_foto is None:
            errores["foto"] = "Usá una imagen PNG, JPG, GIF o WebP válida."
        if not errores:
            try:
                with db.transaccion():
                    db.execute(
                        "UPDATE usuarios SET nombre = :nombre, apellido = :apellido, email = :email,"
                        " carrera_id = :carrera, anio = :anio, comision = :comision WHERE id = :id",
                        nombre=datos["nombre"].strip(),
                        apellido=datos["apellido"].strip(),
                        email=email,
                        carrera=int(carrera_id),
                        anio=int(datos["anio"]),
                        comision=datos["comision"].strip(),
                        id=usuario_id,
                    )
                    db.execute("DELETE FROM catedras WHERE usuario_id = :id", id=usuario_id)
                    for materia_id in materias_validas:
                        db.execute(
                            "INSERT INTO catedras (usuario_id, materia_id)"
                            " VALUES (:usuario, :materia)",
                            usuario=usuario_id,
                            materia=materia_id,
                        )
                    if contenido_foto:
                        db.execute("DELETE FROM fotos_perfil WHERE usuario_id = :id", id=usuario_id)
                        db.execute(
                            "INSERT INTO fotos_perfil (usuario_id, tipo, contenido, actualizado)"
                            " VALUES (:id, :tipo, :contenido, :actualizado)",
                            id=usuario_id,
                            tipo=tipo_foto,
                            contenido=contenido_foto,
                            actualizado=_ahora(),
                        )
            except db.ErrorIntegridad:
                errores["email"] = "Ese email ya está registrado."
            else:
                flash("Tu perfil quedó actualizado.")
                return redirect(url_for("perfil.ver", usuario_id=usuario_id))
    else:
        datos = estudiante

    carreras = db.query("SELECT id, nombre FROM carreras WHERE activa = 1 ORDER BY nombre")
    carrera_seleccionada = str(datos.get("carrera_id") or "").strip()
    carrera_materias_id = int(carrera_seleccionada) if carrera_seleccionada.isdecimal() else -1
    materias_disponibles = db.query(
        "SELECT m.id, m.nombre, m.carrera_id, c.nombre AS carrera FROM materias m"
        " JOIN carreras c ON c.id = m.carrera_id"
        " WHERE m.activa = 1 AND c.activa = 1 AND m.carrera_id = :carrera"
        " ORDER BY m.nombre",
        carrera=carrera_materias_id,
    )
    return render_template(
        "perfil/editar.html",
        estudiante=estudiante,
        datos=datos,
        errores=errores,
        carreras=carreras,
        materias=materias_disponibles,
        materias_seleccionadas=seleccionadas,
    )


@bp.get("/<int:usuario_id>/materias")
@seguridad.requiere_login
def materias_de_carrera(usuario_id: int):
    if g.usuario["id"] != usuario_id:
        abort(403)
    carrera = request.args.get("carrera_id", "")
    if not carrera.isdecimal():
        abort(400)
    filas = db.query(
        "SELECT m.id, m.nombre FROM materias m JOIN carreras c ON c.id = m.carrera_id"
        " WHERE m.carrera_id = :carrera AND m.activa = 1 AND c.activa = 1"
        " ORDER BY m.nombre",
        carrera=int(carrera),
    )
    return jsonify(filas)


@bp.post("/<int:usuario_id>/conexiones")
@seguridad.requiere_login
def solicitar_conexion(usuario_id: int):
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
                creado=_ahora(),
            )
        except db.ErrorIntegridad:
            flash("Ya existe una solicitud o conexión entre ustedes.")
        else:
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
    flash("Conexión aceptada." if estado == "aceptada" else "Solicitud rechazada.")
    return redirect(url_for("perfil.ver", usuario_id=usuario_id))


@bp.post("/<int:usuario_id>/conexiones/<int:solicitante_id>/aceptar")
@seguridad.requiere_login
def aceptar_conexion(usuario_id: int, solicitante_id: int):
    return _resolver_solicitud(usuario_id, solicitante_id, "aceptada")


@bp.post("/<int:usuario_id>/conexiones/<int:solicitante_id>/rechazar")
@seguridad.requiere_login
def rechazar_conexion(usuario_id: int, solicitante_id: int):
    return _resolver_solicitud(usuario_id, solicitante_id, "rechazada")


@bp.route("/<int:usuario_id>/chat", methods=("GET", "POST"))
@seguridad.requiere_login
def chat(usuario_id: int):
    if usuario_id == g.usuario["id"] or _estudiante_publico(usuario_id) is None:
        abort(404)
    error = None
    cuerpo = (request.form.get("cuerpo") or "").strip()
    if request.method == "POST":
        if not cuerpo or len(cuerpo) > 2000:
            error = "El mensaje debe tener entre 1 y 2000 caracteres."
        else:
            db.execute(
                "INSERT INTO mensajes (emisor_id, receptor_id, cuerpo, creado)"
                " VALUES (:emisor, :receptor, :cuerpo, :creado)",
                emisor=g.usuario["id"],
                receptor=usuario_id,
                cuerpo=cuerpo,
                creado=_ahora(),
            )
            return redirect(url_for("perfil.chat", usuario_id=usuario_id))
    mensajes = db.query(
        "SELECT emisor_id, receptor_id, cuerpo, creado FROM mensajes"
        " WHERE (emisor_id = :yo AND receptor_id = :otro)"
        " OR (emisor_id = :otro AND receptor_id = :yo) ORDER BY creado, id",
        yo=g.usuario["id"],
        otro=usuario_id,
    )
    return render_template(
        "perfil/chat.html",
        estudiante=_estudiante_publico(usuario_id),
        mensajes=mensajes,
        error=error,
        cuerpo=cuerpo,
    )


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
