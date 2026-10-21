from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from davincihub import db, seguridad
from davincihub.usuarios import datos

bp = Blueprint("usuarios", __name__, url_prefix="/admin/usuarios")

POR_PAGINA = 10


def _filtros(args) -> dict:
    rol = args.get("rol", "")
    estado = args.get("estado", "")
    return {
        "q": args.get("q", "").strip()[:100],
        "carrera": args.get("carrera", type=int),
        "rol": rol if rol in datos.ROLES else "",
        "estado": estado if estado in datos.ESTADOS else "",
    }


@bp.route("/")
@seguridad.requiere_admin
def lista():
    filtros = _filtros(request.args)
    criterios = (filtros["q"], filtros["carrera"], filtros["rol"], filtros["estado"])
    total = datos.contar_usuarios(*criterios)
    paginas = max(1, -(-total // POR_PAGINA))
    pagina = min(max(request.args.get("pagina", 1, type=int) or 1, 1), paginas)
    return render_template(
        "usuarios/lista.html",
        usuarios=datos.listar_usuarios(*criterios, limite=POR_PAGINA, salto=(pagina - 1) * POR_PAGINA),
        total=total,
        pagina=pagina,
        paginas=paginas,
        filtros=filtros,
        carreras=db.query("SELECT id, nombre FROM carreras ORDER BY nombre"),
    )


@bp.route("/<int:usuario_id>")
@seguridad.requiere_admin
def ficha(usuario_id: int):
    usuario = datos.obtener_usuario(usuario_id)
    if usuario is None:
        abort(404)
    return render_template(
        "usuarios/ficha.html",
        usuario=usuario,
        resumen=datos.resumen_actividad(usuario_id),
        historial=datos.historial_bloqueos(usuario_id),
        cursados=datos.anios_cursados(usuario),
        plan=datos.materias_por_anio(usuario["carrera_id"]) if usuario["carrera_id"] else [],
    )


@bp.route("/<int:usuario_id>/bloqueo", methods=("POST",))
@seguridad.requiere_admin
def bloqueo(usuario_id: int):
    bloquear = request.form.get("accion") == "bloquear"
    try:
        datos.cambiar_bloqueo(usuario_id, g.usuario["id"], bloquear, request.form.get("motivo", ""))
    except datos.ErrorUsuario as error:
        flash(str(error), "error")
    else:
        flash("Cuenta bloqueada. La sesión se cierra en su próxima acción." if bloquear else "Cuenta desbloqueada.")
    return redirect(url_for("usuarios.ficha", usuario_id=usuario_id))


@bp.route("/<int:usuario_id>/catedra", methods=("POST",))
@seguridad.requiere_admin
def catedra(usuario_id: int):
    nombrar = request.form.get("accion") == "nombrar"
    try:
        datos.cambiar_catedra(usuario_id, nombrar)
    except datos.ErrorUsuario as error:
        flash(str(error), "error")
    else:
        flash("Ahora es estudiante de cátedra." if nombrar else "Ya no es estudiante de cátedra.")
    return redirect(url_for("usuarios.ficha", usuario_id=usuario_id))
