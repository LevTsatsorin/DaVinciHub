# pyrefly: ignore[missing-import]
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from davincihub import seguridad
from davincihub.actividades import datos

bp = Blueprint("actividades", __name__)


# ---------------------------------------------------------------------------
# Vistas públicas (requieren login)
# ---------------------------------------------------------------------------


@bp.route("/actividades/")
@seguridad.requiere_login
def lista():
    actividades = datos.listar_actividades_publicas()
    mis_ids = {
        i["id"]
        for i in datos.listar_inscripciones_de(g.usuario["id"])
    }
    return render_template(
        "actividades/lista.html",
        actividades=actividades,
        mis_ids=mis_ids,
    )


@bp.route("/actividades/<int:actividad_id>")
@seguridad.requiere_login
def detalle(actividad_id: int):
    actividad = datos.obtener_actividad(actividad_id)
    if actividad is None:
        abort(404)
    # Solo mostrar aprobadas a estudiantes; admin ve todo
    if actividad["estado"] != "aprobada" and g.usuario["rol"] != "admin":
        if actividad["creador_id"] != g.usuario["id"]:
            abort(404)
    inscripto = datos.esta_inscripto(actividad_id, g.usuario["id"])
    return render_template(
        "actividades/detalle.html",
        actividad=actividad,
        inscripto=inscripto,
    )


@bp.route("/actividades/<int:actividad_id>/inscriptos")
@seguridad.requiere_login
def inscriptos(actividad_id: int):
    actividad = datos.obtener_actividad(actividad_id)
    if actividad is None:
        abort(404)
    es_creador = actividad["creador_id"] == g.usuario["id"]
    if not es_creador and g.usuario["rol"] != "admin":
        abort(403)
    lista_inscriptos = datos.listar_inscriptos(actividad_id)
    return render_template(
        "actividades/inscriptos.html",
        actividad=actividad,
        inscriptos=lista_inscriptos,
    )


@bp.route("/mis-actividades/")
@seguridad.requiere_login
def mis_actividades():
    inscripciones = datos.listar_inscripciones_de(g.usuario["id"])
    creadas = datos.listar_actividades_creadas_por(g.usuario["id"])
    return render_template(
        "actividades/mis_actividades.html",
        inscripciones=inscripciones,
        creadas=creadas,
    )


# ---------------------------------------------------------------------------
# Acciones: inscribir / dar de baja (POST)
# ---------------------------------------------------------------------------


@bp.route("/actividades/<int:actividad_id>/inscribir", methods=("POST",))
@seguridad.requiere_login
def inscribir(actividad_id: int):
    try:
        datos.inscribir(actividad_id, g.usuario["id"])
        flash("¡Te inscribiste correctamente!")
    except datos.ErrorInscripcion as e:
        flash(str(e), "error")
    return redirect(url_for("actividades.detalle", actividad_id=actividad_id))


@bp.route("/actividades/<int:actividad_id>/baja", methods=("POST",))
@seguridad.requiere_login
def baja(actividad_id: int):
    try:
        datos.dar_de_baja(actividad_id, g.usuario["id"])
        flash("Diste de baja tu inscripción.")
    except datos.ErrorInscripcion as e:
        flash(str(e), "error")
    return redirect(url_for("actividades.detalle", actividad_id=actividad_id))


# ---------------------------------------------------------------------------
# Creación de actividades (cualquier usuario logueado)
# ---------------------------------------------------------------------------


@bp.route("/actividades/nueva", methods=("GET", "POST"))
@seguridad.requiere_login
def nueva():
    error = None
    if request.method == "POST":
        try:
            actividad_id = datos.crear_actividad(
                creador_id=g.usuario["id"],
                nombre=request.form.get("nombre", ""),
                descripcion=request.form.get("descripcion", ""),
                inicio=request.form.get("inicio", ""),
                fin=request.form.get("fin") or None,
                ubicacion=request.form.get("ubicacion", ""),
                cupo_maximo=request.form.get("cupo_maximo", 0),
            )
            flash("Actividad enviada. Quedará visible cuando un admin la apruebe.")
            return redirect(url_for("actividades.detalle", actividad_id=actividad_id))
        except datos.ErrorActividad as e:
            error = str(e)
    return render_template("actividades/form.html", actividad=None, error=error)


# ---------------------------------------------------------------------------
# Administración (solo admin)
# ---------------------------------------------------------------------------


@bp.route("/admin/actividades/")
@seguridad.requiere_admin
def admin_lista():
    estado = request.args.get("estado") or "pendiente"
    todas = datos.listar_actividades_admin()
    por_estado = [a for a in todas if a["estado"] == estado]
    conteos = {}
    for a in todas:
        conteos[a["estado"]] = conteos.get(a["estado"], 0) + 1
    return render_template(
        "actividades/admin_lista.html",
        actividades=por_estado,
        estado_actual=estado,
        conteos=conteos,
    )


@bp.route("/admin/actividades/<int:actividad_id>/estado", methods=("POST",))
@seguridad.requiere_admin
def admin_estado(actividad_id: int):
    nuevo_estado = request.form.get("estado", "")
    motivo = request.form.get("motivo", "").strip() or None
    try:
        datos.cambiar_estado(actividad_id, nuevo_estado, motivo)
        flash(f"Actividad marcada como {nuevo_estado}.")
    except datos.ErrorActividad as e:
        flash(str(e), "error")
    return redirect(url_for("actividades.admin_lista"))
