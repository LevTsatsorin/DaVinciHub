from io import BytesIO

from flask import Blueprint, abort, flash, g, redirect, render_template, request, send_file, url_for

from davincihub import db, seguridad
from davincihub.foro import datos
from davincihub.utiles import tipo_imagen

bp = Blueprint("foro", __name__, url_prefix="/foro")
MAX_IMAGEN_BYTES = 3 * 1024 * 1024


def _materias_formulario() -> list[dict]:
    return datos.materias_para_formulario()


def _pregunta_o_404(pregunta_id: int) -> dict:
    pregunta = datos.obtener_pregunta(pregunta_id)
    if pregunta is None:
        abort(404)
    return pregunta


def _exigir_autor(pregunta: dict) -> None:
    if pregunta["autor_id"] != g.usuario["id"]:
        abort(403)


def _leer_imagen():
    archivo = request.files.get("imagen")
    if archivo is None or not archivo.filename:
        return None, None, None
    imagen = archivo.read(MAX_IMAGEN_BYTES + 1)
    if len(imagen) > MAX_IMAGEN_BYTES:
        return None, None, "La imagen supera el tamaño máximo permitido de 3 MB."
    imagen_tipo = tipo_imagen(imagen)
    if imagen_tipo is None:
        return None, None, "Usá una imagen PNG, JPG, GIF o WebP válida."
    return imagen_tipo, imagen, None


def _edicion_cerrada(pregunta_id: int):
    flash("La pregunta ya tiene una respuesta aceptada y no se puede editar.", "error")
    return redirect(url_for("foro.detalle", pregunta_id=pregunta_id))


@bp.get("/")
def index():
    q = (request.args.get("q") or "").strip()[:100]
    mis_dudas = request.args.get("mis_dudas") == "1"
    carrera_texto = (request.args.get("carrera_id") or "").strip()
    materia_texto = (request.args.get("materia_id") or "").strip()
    carrera_id = int(carrera_texto) if carrera_texto.isdecimal() else None
    materia_id = int(materia_texto) if materia_texto.isdecimal() else None
    cuatrimestre_texto = (request.args.get("cuatrimestre") or "").strip()
    cuatrimestre = int(cuatrimestre_texto) if cuatrimestre_texto.isdecimal() else None
    materias = datos.materias_para_formulario() if g.usuario else []
    preguntas = []
    if g.usuario:
        autor_id = g.usuario["id"] if mis_dudas else None
        preguntas = datos.listar_preguntas(q, carrera_id, materia_id, autor_id, cuatrimestre)
    return render_template(
        "foro/index.html",
        preguntas=preguntas,
        q=q,
        materias=materias,
        carrera_id=carrera_texto,
        materia_id=materia_texto,
        cuatrimestre=cuatrimestre_texto,
        mis_dudas=mis_dudas,
    )


@bp.route("/preguntas/nueva", methods=("GET", "POST"))
@seguridad.requiere_login
def nueva_pregunta():
    materias = _materias_formulario()
    error = None
    if request.method == "POST":
        imagen_tipo, imagen, error = _leer_imagen()
        try:
            if error:
                raise datos.ErrorForo(error)
            pregunta_id = datos.crear_pregunta(
                g.usuario["id"], request.form, imagen_tipo, imagen
            )
        except datos.ErrorForo as e:
            error = str(e)
        else:
            flash("Tu pregunta quedó publicada.")
            return redirect(url_for("foro.detalle", pregunta_id=pregunta_id))
    return render_template(
        "foro/pregunta_form.html",
        pregunta=None,
        materias=materias,
        error=error,
        datos_form=request.form,
    )


@bp.get("/preguntas/<int:pregunta_id>")
@seguridad.requiere_login
def detalle(pregunta_id: int):
    pregunta = _pregunta_o_404(pregunta_id)
    respuestas = datos.listar_respuestas(pregunta_id, g.usuario["id"])
    autores = datos.autores({pregunta["autor_id"], *(r["autor_id"] for r in respuestas)}, g.usuario["id"])
    return render_template("foro/detalle.html", pregunta=pregunta, respuestas=respuestas, autores=autores)


@bp.get("/preguntas/<int:pregunta_id>/imagen")
@seguridad.requiere_login
def imagen_pregunta(pregunta_id: int):
    imagen = db.query_one(
        "SELECT imagen_tipo, imagen FROM preguntas WHERE id = :id",
        id=pregunta_id,
    )
    if imagen is None or not imagen["imagen"] or not imagen["imagen_tipo"]:
        abort(404)
    respuesta = send_file(
        BytesIO(bytes(imagen["imagen"])),
        mimetype=imagen["imagen_tipo"],
        max_age=0,
    )
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    return respuesta


@bp.route("/preguntas/<int:pregunta_id>/editar", methods=("GET", "POST"))
@seguridad.requiere_login
def editar_pregunta(pregunta_id: int):
    pregunta = _pregunta_o_404(pregunta_id)
    _exigir_autor(pregunta)
    if request.method == "GET" and pregunta["respuesta_aceptada_id"]:
        return _edicion_cerrada(pregunta_id)
    error = None
    formulario = request.form if request.method == "POST" else pregunta
    if request.method == "POST":
        imagen_tipo, imagen, error = _leer_imagen()
        try:
            if error:
                raise datos.ErrorForo(error)
            datos.editar_pregunta(
                pregunta_id, g.usuario["id"], request.form, imagen_tipo, imagen
            )
        except datos.ErrorForo as e:
            error = str(e)
        else:
            flash("Tu pregunta fue actualizada.")
            return redirect(url_for("foro.detalle", pregunta_id=pregunta_id))
    return render_template(
        "foro/pregunta_form.html",
        pregunta=pregunta,
        materias=_materias_formulario(),
        error=error,
        datos_form=formulario,
    )


@bp.post("/preguntas/<int:pregunta_id>/responder")
@seguridad.requiere_login
def responder(pregunta_id: int):
    _pregunta_o_404(pregunta_id)
    try:
        datos.crear_respuesta(pregunta_id, g.usuario["id"], request.form.get("cuerpo"))
    except datos.ErrorForo as e:
        flash(str(e), "error")
    else:
        flash("Tu respuesta quedó publicada.")
    return redirect(url_for("foro.detalle", pregunta_id=pregunta_id))


@bp.post("/respuestas/<int:respuesta_padre_id>/responder")
@seguridad.requiere_login
def responder_respuesta(respuesta_padre_id: int):
    padre = datos.obtener_respuesta(respuesta_padre_id)
    if padre is None:
        abort(404)
    try:
        datos.crear_respuesta(
            padre["pregunta_id"],
            g.usuario["id"],
            request.form.get("cuerpo"),
            respuesta_padre_id,
        )
    except datos.SinPermisoForo:
        abort(403)
    except datos.ErrorForo as e:
        flash(str(e), "error")
    else:
        flash("Tu respuesta quedó publicada.")
    return redirect(url_for("foro.detalle", pregunta_id=padre["pregunta_id"]))


@bp.route("/respuestas/<int:respuesta_id>/editar", methods=("GET", "POST"))
@seguridad.requiere_login
def editar_respuesta(respuesta_id: int):
    respuesta = datos.obtener_respuesta(respuesta_id)
    if respuesta is None:
        abort(404)
    if respuesta["autor_id"] != g.usuario["id"]:
        abort(403)
    if request.method == "GET" and _pregunta_o_404(respuesta["pregunta_id"])["respuesta_aceptada_id"]:
        return _edicion_cerrada(respuesta["pregunta_id"])
    error = None
    cuerpo = request.form.get("cuerpo", respuesta["cuerpo"])
    if request.method == "POST":
        try:
            datos.editar_respuesta(respuesta_id, g.usuario["id"], request.form.get("cuerpo"))
        except datos.ErrorForo as e:
            error = str(e)
        else:
            flash("Tu respuesta fue actualizada.")
            return redirect(url_for("foro.detalle", pregunta_id=respuesta["pregunta_id"]))
    return render_template("foro/respuesta_form.html", respuesta=respuesta, cuerpo=cuerpo, error=error)


@bp.post("/respuestas/<int:respuesta_id>/aceptar")
@seguridad.requiere_login
def aceptar_respuesta(respuesta_id: int):
    respuesta = datos.obtener_respuesta(respuesta_id)
    if respuesta is None:
        abort(404)
    aceptada_texto = request.form.get("aceptada")
    if aceptada_texto not in ("0", "1"):
        abort(400)
    try:
        aceptada = datos.establecer_aceptacion(
            respuesta_id, g.usuario["id"], aceptada_texto == "1"
        )
    except datos.SinPermisoForo:
        abort(403)
    except datos.ErrorForo as e:
        flash(str(e), "error")
        return redirect(url_for("foro.detalle", pregunta_id=respuesta["pregunta_id"]))
    flash("Respuesta aceptada." if aceptada else "Se quitó la aceptación de la respuesta.")
    return redirect(url_for("foro.detalle", pregunta_id=respuesta["pregunta_id"]))


@bp.post("/respuestas/<int:respuesta_id>/util")
@seguridad.requiere_login
def valorar_respuesta(respuesta_id: int):
    respuesta = datos.obtener_respuesta(respuesta_id)
    if respuesta is None:
        abort(404)
    try:
        valorada = datos.valorar_respuesta(respuesta_id, g.usuario["id"])
    except datos.SinPermisoForo:
        abort(403)
    flash("Marcaste la respuesta como útil." if valorada else "Ya habías valorado esta respuesta.")
    return redirect(url_for("foro.detalle", pregunta_id=respuesta["pregunta_id"]))
