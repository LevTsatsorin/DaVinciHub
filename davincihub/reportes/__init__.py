from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from davincihub import seguridad
from davincihub.reportes import datos

bp = Blueprint("reportes", __name__, url_prefix="/reportes")
bp.add_app_template_global(datos.MOTIVOS, "motivos_reporte")

ESTADOS = {"pendiente": "Pendientes", "resuelto": "Resueltos"}


@bp.app_context_processor
def contexto_motivos():
    ctx: dict = {"motivos_reporte": datos.MOTIVOS}
    from flask import g
    usuario = g.get("usuario")
    if usuario and usuario.get("rol") == "admin":
        ctx["contar_reportes_pendientes"] = datos.contar_pendientes()
    return ctx


@bp.post("/crear")
@seguridad.requiere_login
def crear():
    tipo_objeto = request.form.get("tipo_objeto", "")
    objeto_id_texto = request.form.get("objeto_id", "")
    motivo = request.form.get("motivo", "").strip()
    siguiente = request.form.get("siguiente") or "/"
    if not objeto_id_texto.isdecimal():
        flash("Datos inválidos.", "error")
        return redirect(siguiente)
    try:
        datos.crear_reporte(g.usuario["id"], tipo_objeto, int(objeto_id_texto), motivo)
        flash("Gracias por tu reporte. El equipo lo va a revisar.")
    except datos.ErrorReporte as e:
        flash(str(e), "error")
    return redirect(siguiente)


@bp.get("/admin")
@seguridad.requiere_admin
def admin_cola():
    estado = request.args.get("estado", "pendiente")
    if estado not in ESTADOS:
        estado = "pendiente"
    reportes = datos.listar_reportes(estado)
    return render_template(
        "reportes/admin_cola.html",
        reportes=reportes,
        estado=estado,
        estados=ESTADOS,
        pendientes=datos.contar_pendientes(),
        motivos=datos.MOTIVOS,
    )


@bp.post("/<int:reporte_id>/resolver")
@seguridad.requiere_admin
def resolver(reporte_id: int):
    accion = request.form.get("accion", "")
    resolucion = request.form.get("resolucion", "").strip()
    try:
        if accion == "bloquear":
            reporte = datos.obtener_reporte(reporte_id)
            if reporte is None:
                abort(404)
            usuario_obj_id = _obtener_usuario_del_objeto(reporte["tipo_objeto"], reporte["objeto_id"])
            if usuario_obj_id is None:
                flash("No se puede identificar el usuario del contenido.", "error")
                return redirect(url_for("reportes.admin_cola"))
            if usuario_obj_id == g.usuario["id"]:
                flash("No podés derivar a bloqueo tu propia cuenta.", "error")
                return redirect(url_for("reportes.admin_cola"))
            datos.resolver_reporte(
                reporte_id, g.usuario["id"], "bloquear",
                f"Derivado a bloqueo: {resolucion}" if resolucion else "Derivado a bloqueo de cuenta."
            )
            flash("Reporte derivado a bloqueo. Completá la acción en la ficha del usuario.")
            return redirect(url_for("usuarios.ficha", usuario_id=usuario_obj_id, motivo=resolucion))
        datos.resolver_reporte(reporte_id, g.usuario["id"], accion, resolucion)
        if accion == "ocultar":
            flash("Contenido ocultado. Ya no es visible para los estudiantes.")
        else:
            flash("Reporte descartado.")
    except datos.ErrorReporte as e:
        flash(str(e), "error")
    return redirect(url_for("reportes.admin_cola"))


@bp.post("/<int:reporte_id>/restaurar")
@seguridad.requiere_admin
def restaurar(reporte_id: int):
    reporte = datos.obtener_reporte(reporte_id)
    if reporte is None:
        abort(404)
    try:
        datos.restaurar_contenido(reporte["tipo_objeto"], reporte["objeto_id"])
        flash("Contenido restaurado y visible nuevamente.")
    except datos.ErrorReporte as e:
        flash(str(e), "error")
    return redirect(url_for("reportes.admin_cola", estado="resuelto"))


def _obtener_usuario_del_objeto(tipo_objeto: str, objeto_id: int) -> int | None:
    from davincihub import db
    mapas = {
        "publicacion": ("publicaciones", "autor_id"),
        "pregunta": ("preguntas", "autor_id"),
        "respuesta": ("respuestas", "autor_id"),
        "actividad": ("actividades", "creador_id"),
        "usuario": ("usuarios", "id"),
    }
    if tipo_objeto not in mapas:
        return None
    tabla, columna = mapas[tipo_objeto]
    fila = db.query_one(f"SELECT {columna} AS uid FROM {tabla} WHERE id = :id", id=objeto_id)
    return fila["uid"] if fila else None
