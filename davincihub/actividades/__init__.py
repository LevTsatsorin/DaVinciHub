from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from davincihub import seguridad
from davincihub.actividades.datos import (
    ErrorActividad,
    aprobar_actividad,
    contar_actividades_por_estado,
    crear_actividad,
    listar_actividades_admin,
    listar_actividades_creador,
    listar_actividades_publicas,
    obtener_actividad,
    rechazar_actividad,
)
from davincihub.utiles import ahora_local

bp = Blueprint("actividades", __name__, url_prefix="/actividades")

ESTADOS_MODERACION = {"pendiente": "Pendientes", "aprobada": "Aprobadas", "rechazada": "Rechazadas"}


@bp.route("/")
def index():
    """Listado público de actividades aprobadas."""
    actividades = listar_actividades_publicas()
    return render_template("actividades/index.html", actividades=actividades)


@bp.route("/<int:actividad_id>")
def detalle(actividad_id: int):
    """Detalle de una actividad.

    RN-11 / CA-08: Sólo las actividades aprobadas son visibles para todos.
    Una actividad pendiente o rechazada no es accesible por URL directa para otros estudiantes;
    únicamente la puede ver su creador o un admin.
    """
    actividad = obtener_actividad(actividad_id)
    if not actividad:
        abort(404)

    if actividad["estado"] != "aprobada":
        usuario = g.get("usuario")
        if not usuario:
            abort(404)
        es_admin = usuario.get("rol") == "admin"
        es_creador = usuario.get("id") == actividad["creador_id"]
        if not (es_admin or es_creador):
            abort(404)

    return render_template("actividades/detalle.html", actividad=actividad)


@bp.route("/crear", methods=("GET", "POST"))
@seguridad.requiere_login
def crear():
    """Creación de una nueva actividad por parte de un estudiante."""
    errores = {}
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        inicio = request.form.get("inicio", "").strip()
        fin = request.form.get("fin", "").strip() or None
        ubicacion = request.form.get("ubicacion", "").strip()
        cupo_raw = request.form.get("cupo_maximo", "").strip()

        if not nombre:
            errores["nombre"] = "El nombre es obligatorio."
        if not descripcion:
            errores["descripcion"] = "La descripción es obligatoria."
        if not inicio:
            errores["inicio"] = "La fecha y hora de inicio son obligatorias."
        if not ubicacion:
            errores["ubicacion"] = "La ubicación es obligatoria."
        if not cupo_raw:
            errores["cupo_maximo"] = "El cupo máximo es obligatorio."
        elif not cupo_raw.isdecimal() or not cupo_raw.isascii() or int(cupo_raw) < 1:
            errores["cupo_maximo"] = "El cupo máximo debe ser un número entero mayor a 0."

        if not errores:
            try:
                crear_actividad(
                    creador_id=g.usuario["id"],
                    nombre=nombre,
                    descripcion=descripcion,
                    inicio=inicio,
                    fin=fin,
                    ubicacion=ubicacion,
                    cupo_maximo=int(cupo_raw),
                )
                flash("¡Actividad enviada! Quedó pendiente de aprobación por la escuela.")
                return redirect(url_for("actividades.mis_actividades"))
            except ErrorActividad as e:
                flash(str(e), "error")

    return render_template(
        "actividades/crear.html", errores=errores, datos=request.form, minimo=ahora_local()[:16]
    )


@bp.route("/mis-actividades")
@seguridad.requiere_login
def mis_actividades():
    """El creador ve el estado de sus actividades (pendiente, aprobada, rechazada)."""
    actividades = listar_actividades_creador(g.usuario["id"])
    return render_template("actividades/mis_actividades.html", actividades=actividades)


@bp.route("/admin")
@seguridad.requiere_admin
def admin_panel():
    """Panel de administración para ver todas las actividades."""
    estado_filtro = request.args.get("estado")
    if estado_filtro not in ESTADOS_MODERACION:
        estado_filtro = None
    return render_template(
        "actividades/admin.html",
        actividades=listar_actividades_admin(estado=estado_filtro),
        estado_filtro=estado_filtro,
        totales=contar_actividades_por_estado(),
        estados=ESTADOS_MODERACION,
    )


@bp.route("/admin/<int:actividad_id>/aprobar", methods=("POST",))
@seguridad.requiere_admin
def aprobar(actividad_id: int):
    """El admin aprueba la actividad."""
    try:
        aprobar_actividad(actividad_id)
        flash("Actividad aprobada y publicada.")
    except ErrorActividad as e:
        flash(str(e), "error")
    return redirect(url_for("actividades.admin_panel"))


@bp.route("/admin/<int:actividad_id>/rechazar", methods=("POST",))
@seguridad.requiere_admin
def rechazar(actividad_id: int):
    """El admin rechaza la actividad indicando un motivo obligatorio (RF-22)."""
    motivo = request.form.get("motivo", "").strip()
    if not motivo:
        flash("Debés indicar un motivo para rechazar la actividad.", "error")
        return redirect(url_for("actividades.admin_panel"))

    try:
        rechazar_actividad(actividad_id, motivo=motivo)
        flash("Actividad rechazada. Se notificó al creador.")
    except ErrorActividad as e:
        flash(str(e), "error")
    return redirect(url_for("actividades.admin_panel"))
