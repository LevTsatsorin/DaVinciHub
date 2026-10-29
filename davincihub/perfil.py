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
from davincihub.notificaciones import notificar
from davincihub.notificaciones import sin_leer as notificaciones_sin_leer
from davincihub.usuarios import datos as usuarios_datos
from davincihub.utiles import (
    ahora,
    ahora_local,
    fecha_corta,
    paginas_visibles,
    sin_acentos,
    tipo_imagen,
)

bp = Blueprint("perfil", __name__, url_prefix="/estudiantes")
MAX_FOTO_BYTES = 3 * 1024 * 1024
ESTUDIANTES_POR_PAGINA = 12
TEMAS_CHAT = {"davinci": "Da Vinci", "menta": "Menta", "violeta": "Violeta", "ambar": "Ámbar", "noche": "Noche"}


def _tipo_foto(contenido: bytes) -> str | None:
    return tipo_imagen(contenido)


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


@bp.get("/buscar")
@seguridad.requiere_login
def buscar_estudiantes():
    if g.usuario["rol"] != "estudiante":
        abort(403)
    filtros = {
        "q": (request.args.get("q") or "").strip()[:100],
        "carrera": request.args.get("carrera", type=int),
        "anio": request.args.get("anio", type=int),
        "comision": (request.args.get("comision") or "").strip()[:40],
    }
    condiciones = ["u.rol = 'estudiante'", "u.bloqueado = 0", "u.id <> :yo"]
    params = {"yo": g.usuario["id"]}
    buscado = sin_acentos(filtros["q"])
    if buscado:
        nombre = db.sql_sin_acentos("u.nombre || ' ' || u.apellido")
        escapado = buscado.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        condiciones.append(f"{nombre} LIKE :buscado ESCAPE '\\'")
        params["buscado"] = f"%{escapado}%"
    if filtros["carrera"]:
        condiciones.append("u.carrera_id = :carrera")
        params["carrera"] = filtros["carrera"]
    else:
        filtros["carrera"] = None
    if filtros["anio"] and 1 <= filtros["anio"] <= 6:
        condiciones.append("u.anio = :anio")
        params["anio"] = filtros["anio"]
    else:
        filtros["anio"] = None
    if filtros["comision"]:
        condiciones.append("lower(trim(u.comision)) = :comision")
        params["comision"] = filtros["comision"].lower()
    desde_sql = (
        " FROM usuarios u LEFT JOIN carreras c ON c.id = u.carrera_id"
        " LEFT JOIN conexiones x ON (x.solicitante_id = :yo AND x.receptor_id = u.id)"
        " OR (x.solicitante_id = u.id AND x.receptor_id = :yo)"
        f" WHERE {' AND '.join(condiciones)}"
    )
    conteo = db.query_one(
        "SELECT COUNT(*) AS total, COALESCE(SUM(CASE WHEN x.estado = 'aceptada' THEN 1 ELSE 0 END), 0) AS conexiones"
        + desde_sql,
        **params,
    )
    cantidades = {"conexiones": conteo["conexiones"], "otros": conteo["total"] - conteo["conexiones"]}
    vista = "conexiones" if request.args.get("vista") == "conexiones" else "otros"
    paginas = max(1, -(-cantidades[vista] // ESTUDIANTES_POR_PAGINA))
    pagina = min(max(request.args.get("pagina", 1, type=int) or 1, 1), paginas)
    pestana = "x.estado = 'aceptada'" if vista == "conexiones" else "(x.estado IS NULL OR x.estado <> 'aceptada')"
    estudiantes = db.query(
        "SELECT u.id, u.nombre, u.apellido, u.anio, u.comision, c.nombre AS carrera,"
        " EXISTS (SELECT 1 FROM fotos_perfil f WHERE f.usuario_id = u.id) AS tiene_foto,"
        " x.estado AS conexion_estado, x.solicitante_id"
        + desde_sql + f" AND {pestana}"
        " ORDER BY u.apellido, u.nombre, u.id LIMIT :limite OFFSET :desde",
        limite=ESTUDIANTES_POR_PAGINA, desde=(pagina - 1) * ESTUDIANTES_POR_PAGINA, **params,
    )
    argumentos = {k: v for k, v in request.args.items() if k != "pagina" and v}
    enlaces = {
        "anterior": url_for("perfil.buscar_estudiantes", **argumentos, pagina=pagina - 1),
        "siguiente": url_for("perfil.buscar_estudiantes", **argumentos, pagina=pagina + 1),
        "paginas": [
            (numero, url_for("perfil.buscar_estudiantes", **argumentos, pagina=numero) if numero else None)
            for numero in paginas_visibles(pagina, paginas)
        ],
    }
    return render_template(
        "perfil/buscar.html",
        estudiantes=estudiantes,
        cantidades=cantidades,
        vista=vista,
        filtros=filtros,
        pagina=pagina,
        paginas=paginas,
        enlaces=enlaces,
        carreras=db.query("SELECT id, nombre FROM carreras WHERE activa = 1 ORDER BY nombre"),
    )


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
        " WHERE i.usuario_id = :id AND a.estado = 'aprobada' AND a.inicio >= :ahora"
        " ORDER BY a.inicio LIMIT 4",
        id=usuario_id, ahora=ahora_local(),
    )
    totales = db.query_one(
        "SELECT COUNT(*) AS total, COALESCE(SUM(CASE WHEN a.inicio < :ahora THEN 1 ELSE 0 END), 0) AS pasadas"
        " FROM inscripciones i JOIN actividades a ON a.id = i.actividad_id"
        " WHERE i.usuario_id = :id AND a.estado = 'aprobada'",
        id=usuario_id, ahora=ahora_local(),
    )
    actividades_total = totales["total"]
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
        actividades_pasadas=totales["pasadas"],
        proximas_total=totales["total"] - totales["pasadas"],
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
    mensaje = None
    try:
        with db.transaccion():
            if not _bloquear_par(g.usuario["id"], usuario_id):
                abort(404)
            if _estudiante_publico(g.usuario["id"]) is None or _estudiante_publico(usuario_id) is None:
                abort(404)
            conexion = _conexion_par(g.usuario["id"], usuario_id)
            if conexion and conexion["estado"] == "pendiente" and conexion["solicitante_id"] == usuario_id:
                db.execute(
                    "UPDATE conexiones SET estado = 'aceptada' WHERE id = :id AND estado = 'pendiente'",
                    id=conexion["id"],
                )
                notificar(
                    usuario_id,
                    "conexion",
                    f"{g.usuario['nombre']} {g.usuario['apellido']} aceptó tu solicitud de conexión.",
                    url_for("perfil.ver", usuario_id=g.usuario["id"]),
                )
                mensaje = "La solicitud mutua se convirtió en una conexión."
            elif conexion and conexion["estado"] == "rechazada" and conexion["receptor_id"] == g.usuario["id"]:
                db.execute("DELETE FROM conexiones WHERE id = :id", id=conexion["id"])
                mensaje = _crear_solicitud(usuario_id)
            elif conexion:
                mensaje = "Ya existe una solicitud o conexión entre ustedes."
            else:
                mensaje = _crear_solicitud(usuario_id)
    except db.ErrorIntegridad:
        mensaje = "Ya existe una solicitud o conexión entre ustedes."
    if mensaje:
        flash(mensaje)
    return redirect(_volver_local() or url_for("perfil.ver", usuario_id=usuario_id))


def _volver_local() -> str | None:
    destino = request.form.get("volver") or ""
    seguro = destino.startswith("/") and not destino.startswith("//") and "\\" not in destino
    return destino if seguro else None


def _bloquear_par(uno_id: int, otro_id: int) -> bool:
    return all(db.bloquear_fila("usuarios", usuario_id) for usuario_id in sorted((uno_id, otro_id)))


def _conexion_par(uno_id: int, otro_id: int) -> dict | None:
    return db.query_one(
        "SELECT id, solicitante_id, receptor_id, estado FROM conexiones"
        " WHERE (solicitante_id = :uno AND receptor_id = :otro)"
        " OR (solicitante_id = :otro AND receptor_id = :uno)",
        uno=uno_id,
        otro=otro_id,
    )


def _crear_solicitud(otro_id: int):
    db.execute(
        "INSERT INTO conexiones (solicitante_id, receptor_id, estado, creado)"
        " VALUES (:solicitante, :receptor, 'pendiente', :creado)",
        solicitante=g.usuario["id"],
        receptor=otro_id,
        creado=ahora(),
    )
    notificar(
        otro_id,
        "conexion",
        f"{g.usuario['nombre']} {g.usuario['apellido']} quiere conectar con vos.",
        url_for("perfil.conexiones", usuario_id=otro_id),
    )
    return "Solicitud de conexión enviada."


def _resolver_solicitud(usuario_id: int, solicitante_id: int, estado: str):
    if g.usuario["id"] != usuario_id:
        abort(403)
    if g.usuario["rol"] != "estudiante":
        abort(403)
    with db.transaccion():
        if not _bloquear_par(usuario_id, solicitante_id):
            abort(404)
        if _estudiante_publico(usuario_id) is None or _estudiante_publico(solicitante_id) is None:
            abort(404)
        solicitud = db.query_one(
            "SELECT id FROM conexiones WHERE solicitante_id = :solicitante"
            " AND receptor_id = :receptor AND estado = 'pendiente'",
            solicitante=solicitante_id,
            receptor=usuario_id,
        )
        if solicitud is None:
            abort(404)
        actualizadas = db.execute(
            "UPDATE conexiones SET estado = :estado WHERE id = :id AND estado = 'pendiente'",
            estado=estado,
            id=solicitud["id"],
        )
        if actualizadas != 1:
            abort(404)
        if estado == "aceptada":
            notificar(
                solicitante_id,
                "conexion",
                f"{g.usuario['nombre']} {g.usuario['apellido']} aceptó tu solicitud de conexión.",
                url_for("perfil.ver", usuario_id=usuario_id),
            )
    flash("Conexión aceptada." if estado == "aceptada" else "Solicitud ignorada.")
    return redirect(_volver_local() or url_for("perfil.conexiones", usuario_id=usuario_id))


@bp.post("/<int:usuario_id>/conexiones/<int:solicitante_id>/aceptar")
@seguridad.requiere_login
def aceptar_conexion(usuario_id: int, solicitante_id: int):
    return _resolver_solicitud(usuario_id, solicitante_id, "aceptada")


@bp.post("/<int:usuario_id>/conexiones/<int:solicitante_id>/rechazar")
@seguridad.requiere_login
def rechazar_conexion(usuario_id: int, solicitante_id: int):
    return _resolver_solicitud(usuario_id, solicitante_id, "rechazada")


def _quitar_conexion(usuario_id: int, otro_id: int, cancelar: bool):
    if g.usuario["id"] != usuario_id or g.usuario["rol"] != "estudiante":
        abort(403)
    with db.transaccion():
        if not _bloquear_par(usuario_id, otro_id):
            abort(404)
        if _estudiante_publico(usuario_id) is None or _estudiante_publico(otro_id) is None:
            abort(404)
        if cancelar:
            condiciones = (
                "solicitante_id = :yo AND receptor_id = :otro AND estado IN ('pendiente', 'rechazada')"
            )
        else:
            condiciones = (
                "((solicitante_id = :yo AND receptor_id = :otro)"
                " OR (solicitante_id = :otro AND receptor_id = :yo)) AND estado = 'aceptada'"
            )
        eliminadas = db.execute(
            f"DELETE FROM conexiones WHERE {condiciones}",
            yo=usuario_id,
            otro=otro_id,
        )
        if eliminadas != 1:
            abort(404)
    flash("Solicitud cancelada." if cancelar else "Conexión eliminada.")
    return redirect(_volver_local() or url_for("perfil.conexiones", usuario_id=usuario_id))


@bp.post("/<int:usuario_id>/conexiones/<int:otro_id>/cancelar")
@seguridad.requiere_login
def cancelar_conexion(usuario_id: int, otro_id: int):
    return _quitar_conexion(usuario_id, otro_id, cancelar=True)


@bp.post("/<int:usuario_id>/conexiones/<int:otro_id>/eliminar")
@seguridad.requiere_login
def eliminar_conexion(usuario_id: int, otro_id: int):
    return _quitar_conexion(usuario_id, otro_id, cancelar=False)


@bp.get("/<int:usuario_id>/conexiones")
@seguridad.requiere_login
def conexiones(usuario_id: int):
    if g.usuario["id"] != usuario_id:
        abort(403)
    if g.usuario["rol"] != "estudiante":
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
        " WHERE x.solicitante_id = :id AND x.estado IN ('pendiente', 'rechazada')"
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


def _conversaciones() -> list[dict]:
    return db.query(
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


def _solo_estudiante():
    if g.usuario["rol"] != "estudiante":
        abort(403)


@bp.get("/chats")
@seguridad.requiere_login
def chats():
    _solo_estudiante()
    return render_template("perfil/chats.html", conversaciones=_conversaciones())


@bp.get("/chats/estado")
@seguridad.requiere_login
def chats_estado():
    _solo_estudiante()
    conversaciones = _conversaciones()
    return jsonify(
        avisos=notificaciones_sin_leer(g.usuario["id"]),
        mensajes=sum(c["sin_leer"] for c in conversaciones),
        con_sin_leer=sum(1 for c in conversaciones if c["sin_leer"]),
        conversaciones=len(conversaciones),
        bandeja=render_template("perfil/_bandeja.html", conversaciones=conversaciones),
    )


def _chat_con(usuario_id: int) -> dict:
    _solo_estudiante()
    estudiante = None if usuario_id == g.usuario["id"] else _estudiante_publico(usuario_id)
    if estudiante is None:
        abort(404)
    return estudiante


def _marcar_leidos(otro_id: int):
    with db.transaccion():
        db.execute(
            "UPDATE mensajes SET leido = 1 WHERE receptor_id = :yo AND emisor_id = :otro AND leido = 0",
            yo=g.usuario["id"],
            otro=otro_id,
        )
        db.execute(
            "UPDATE notificaciones SET leida = 1 WHERE usuario_id = :yo AND enlace = :e AND leida = 0",
            yo=g.usuario["id"],
            e=url_for("perfil.chat", usuario_id=otro_id),
        )


MENSAJES_POR_TANDA = 30
MAXIMO_NUEVOS = 200


def _mensajes(otro_id: int, desde: int = 0, antes: int | None = None, limite: int | None = None) -> list[dict]:
    """Mensajes de la conversación en orden; con `antes` o `limite` trae los más recientes de ese tramo."""
    condiciones = "m.id > :desde" + (" AND m.id < :antes" if antes else "")
    orden = " ORDER BY m.id DESC LIMIT :limite" if limite else " ORDER BY m.id"
    filas = db.query(
        "SELECT m.id, m.emisor_id, m.receptor_id, m.cuerpo, m.creado, m.leido,"
        " emisor.nombre AS emisor_nombre, emisor.apellido AS emisor_apellido"
        " FROM mensajes m JOIN usuarios emisor ON emisor.id = m.emisor_id"
        " WHERE ((m.emisor_id = :yo AND m.receptor_id = :otro)"
        f" OR (m.emisor_id = :otro AND m.receptor_id = :yo)) AND {condiciones}{orden}",
        yo=g.usuario["id"],
        otro=otro_id,
        desde=desde,
        antes=antes,
        limite=limite,
    )
    return filas[::-1] if limite else filas


def _hay_anteriores(otro_id: int, primero: int | None) -> bool:
    return primero is not None and db.query_one(
        "SELECT 1 AS hay FROM mensajes WHERE id < :primero AND ((emisor_id = :yo AND receptor_id = :otro)"
        " OR (emisor_id = :otro AND receptor_id = :yo)) LIMIT 1",
        primero=primero, yo=g.usuario["id"], otro=otro_id,
    ) is not None


def _como_json(mensaje: dict) -> dict:
    propio = mensaje["emisor_id"] == g.usuario["id"]
    return {
        "id": mensaje["id"],
        "propio": propio,
        "autor": "Yo" if propio else mensaje["emisor_nombre"],
        "cuerpo": mensaje["cuerpo"],
        "creado": mensaje["creado"],
        "hora": fecha_corta(mensaje["creado"]),
    }


def _enviar(otro_id: int, cuerpo: str) -> dict:
    enlace = url_for("perfil.chat", usuario_id=g.usuario["id"])
    with db.transaccion():
        fila = db.query_one(
            "INSERT INTO mensajes (emisor_id, receptor_id, cuerpo, creado)"
            " VALUES (:emisor, :receptor, :cuerpo, :creado) RETURNING id",
            emisor=g.usuario["id"],
            receptor=otro_id,
            cuerpo=cuerpo,
            creado=ahora(),
        )
        if not db.query_one(
            "SELECT id FROM notificaciones WHERE usuario_id = :u AND enlace = :e AND leida = 0",
            u=otro_id,
            e=enlace,
        ):
            notificar(
                otro_id,
                "mensaje",
                f"{g.usuario['nombre']} {g.usuario['apellido']} te escribió un mensaje.",
                enlace,
            )
    return _mensajes(otro_id, desde=fila["id"] - 1)[0]


@bp.route("/<int:usuario_id>/chat", methods=("GET", "POST"))
@seguridad.requiere_login
def chat(usuario_id: int):
    estudiante = _chat_con(usuario_id)
    por_fetch = request.headers.get("X-Requested-With") == "fetch"
    error = None
    cuerpo = (request.form.get("cuerpo") or "").replace("\r\n", "\n").strip()
    if request.method == "POST":
        if not cuerpo or len(cuerpo) > 2000:
            error = "El mensaje debe tener entre 1 y 2000 caracteres."
            if por_fetch:
                return jsonify(error=error), 400
        else:
            mensaje = _enviar(usuario_id, cuerpo)
            if por_fetch:
                return jsonify(mensaje=_como_json(mensaje)), 201
            return redirect(url_for("perfil.chat", usuario_id=usuario_id))
    primer_nuevo = db.query_one(
        "SELECT MIN(id) AS id, COUNT(*) AS cantidad FROM mensajes"
        " WHERE emisor_id = :otro AND receptor_id = :yo AND leido = 0",
        otro=usuario_id, yo=g.usuario["id"],
    )
    mensajes = _mensajes(usuario_id, limite=MENSAJES_POR_TANDA)
    if primer_nuevo["id"] and (not mensajes or primer_nuevo["id"] < mensajes[0]["id"]):
        contexto = _mensajes(usuario_id, antes=primer_nuevo["id"], limite=5)
        desde = contexto[0]["id"] - 1 if contexto else primer_nuevo["id"] - 1
        mensajes = _mensajes(usuario_id, desde=desde, limite=MAXIMO_NUEVOS + 5)
    _marcar_leidos(usuario_id)
    return render_template(
        "perfil/chat.html",
        temas=TEMAS_CHAT,
        estudiante=estudiante,
        mensajes=mensajes,
        primer_nuevo=primer_nuevo["id"],
        cantidad_nuevos=primer_nuevo["cantidad"],
        hay_anteriores=_hay_anteriores(usuario_id, mensajes[0]["id"] if mensajes else None),
        error=error,
        cuerpo=cuerpo,
    )


@bp.get("/<int:usuario_id>/chat/anteriores")
@seguridad.requiere_login
def chat_anteriores(usuario_id: int):
    _chat_con(usuario_id)
    antes = request.args.get("antes", 0, type=int) or 0
    if antes <= 0:
        abort(400)
    mensajes = _mensajes(usuario_id, antes=antes, limite=MENSAJES_POR_TANDA)
    return jsonify(
        mensajes=[_como_json(m) for m in mensajes],
        hay_mas=_hay_anteriores(usuario_id, mensajes[0]["id"] if mensajes else None),
    )


@bp.get("/<int:usuario_id>/chat/nuevos")
@seguridad.requiere_login
def chat_nuevos(usuario_id: int):
    _chat_con(usuario_id)
    desde = request.args.get("desde", 0, type=int) or 0
    nuevos = _mensajes(usuario_id, desde)
    if any(m["emisor_id"] == usuario_id for m in nuevos):
        _marcar_leidos(usuario_id)
    return jsonify(mensajes=[_como_json(m) for m in nuevos], avisos=notificaciones_sin_leer(g.usuario["id"]))


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
