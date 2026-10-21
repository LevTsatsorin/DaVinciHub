from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from davincihub import seguridad
from davincihub.academico import datos

bp = Blueprint("academico", __name__, url_prefix="/admin/carreras")


def _carrera_o_404(carrera_id: int) -> dict:
    carrera = datos.obtener_carrera(carrera_id)
    if carrera is None:
        abort(404)
    return carrera


def _materia_o_404(materia_id: int) -> dict:
    materia = datos.obtener_materia(materia_id)
    if materia is None:
        abort(404)
    return materia


@bp.route("/")
@seguridad.requiere_admin
def lista():
    estado = "deshabilitadas" if request.args.get("estado") == "deshabilitadas" else "activas"
    todas = datos.listar_carreras()
    activas = [c for c in todas if c["activa"]]
    apagadas = [c for c in todas if not c["activa"]]
    return render_template(
        "academico/lista.html",
        estado=estado,
        carreras=apagadas if estado == "deshabilitadas" else activas,
        total_activas=len(activas),
        total_apagadas=len(apagadas),
    )


CUATRIMESTRES_MAXIMOS = datos.DURACION_MAXIMA * 2


@bp.route("/nueva", methods=("GET", "POST"))
@seguridad.requiere_admin
def nueva():
    materias = {n: request.form.getlist(f"materias-{n}") for n in range(1, CUATRIMESTRES_MAXIMOS + 1)}
    error, paso = None, 1
    if request.method == "POST":
        try:
            carrera_id = datos.crear_carrera_con_plan(request.form, materias)
        except datos.ErrorPlan as e:
            error, paso = str(e), 2
        except datos.ErrorAcademico as e:
            error = str(e)
        else:
            flash("Carrera creada con su plan de estudios.")
            return redirect(url_for("academico.plan", carrera_id=carrera_id))
    return render_template(
        "academico/asistente.html",
        error=error,
        paso=paso,
        datos_form=request.form,
        materias={n: [m for m in nombres if m.strip()] for n, nombres in materias.items()},
        duracion_maxima=datos.DURACION_MAXIMA,
    )


@bp.route("/<int:carrera_id>/editar", methods=("GET", "POST"))
@seguridad.requiere_admin
def editar(carrera_id: int):
    return _formulario_carrera(_carrera_o_404(carrera_id))


def _formulario_carrera(carrera: dict | None):
    error = None
    if request.method == "POST":
        try:
            carrera_id = datos.guardar_carrera(request.form, carrera["id"] if carrera else None)
        except datos.ErrorAcademico as e:
            error = str(e)
        else:
            flash("Carrera guardada." if carrera else "Carrera creada. Ahora cargá su plan de materias.")
            return redirect(url_for("academico.plan", carrera_id=carrera_id))
    return render_template(
        "academico/carrera_form.html",
        carrera=carrera,
        error=error,
        datos_form=request.form if request.method == "POST" else (carrera or {}),
        duracion_maxima=datos.DURACION_MAXIMA,
    )


@bp.route("/<int:carrera_id>")
@seguridad.requiere_admin
def plan(carrera_id: int):
    carrera = _carrera_o_404(carrera_id)
    return render_template("academico/plan.html", carrera=carrera, plan=datos.plan_de_carrera(carrera_id))


@bp.route("/<int:carrera_id>/estado", methods=("POST",))
@seguridad.requiere_admin
def estado(carrera_id: int):
    _carrera_o_404(carrera_id)
    activa = request.form.get("activa") == "1"
    datos.cambiar_estado_carrera(carrera_id, activa)
    if activa:
        flash("Carrera habilitada.")
    return redirect(url_for("academico.plan", carrera_id=carrera_id))


@bp.route("/<int:carrera_id>/materias", methods=("POST",))
@seguridad.requiere_admin
def nueva_materia(carrera_id: int):
    _carrera_o_404(carrera_id)
    try:
        datos.guardar_materia(carrera_id, request.form)
    except datos.ErrorAcademico as e:
        flash(str(e), "error")
    else:
        flash(f"Materia «{request.form['nombre'].strip()}» agregada.")
    return redirect(url_for("academico.plan", carrera_id=carrera_id))


@bp.route("/materias/<int:materia_id>/editar", methods=("GET", "POST"))
@seguridad.requiere_admin
def editar_materia(materia_id: int):
    materia = _materia_o_404(materia_id)
    carrera = datos.obtener_carrera(materia["carrera_id"])
    error = None
    if request.method == "POST":
        try:
            datos.guardar_materia(carrera["id"], request.form, materia_id)
        except datos.ErrorAcademico as e:
            error = str(e)
        else:
            flash("Materia guardada.")
            return redirect(url_for("academico.plan", carrera_id=carrera["id"]))
    return render_template(
        "academico/materia_form.html",
        materia=materia,
        carrera=carrera,
        error=error,
        datos_form=request.form if request.method == "POST" else materia,
    )


@bp.route("/materias/<int:materia_id>/estado", methods=("POST",))
@seguridad.requiere_admin
def estado_materia(materia_id: int):
    materia = _materia_o_404(materia_id)
    activa = request.form.get("activa") == "1"
    datos.cambiar_estado_materia(materia_id, activa)
    flash(f"«{materia['nombre']}» habilitada." if activa else f"«{materia['nombre']}» deshabilitada.")
    return redirect(url_for("academico.plan", carrera_id=materia["carrera_id"]))
