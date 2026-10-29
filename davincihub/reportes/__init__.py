from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from davincihub import seguridad
from davincihub.reportes import datos

bp = Blueprint("reportes", __name__, url_prefix="/reportes")

ESTADOS = {"pendiente": "Pendientes", "resuelto": "Resueltos"}
POR_PAGINA = 10


def _ruta_local(destino: str | None) -> str:
    destino = destino or ""
    if destino.startswith("/") and not destino.startswith("//") and "\\" not in destino:
        return destino
    return url_for("inicio")


@bp.app_context_processor
def contexto_reportes():
    usuario = g.get("usuario")
    contexto = {"motivos_reporte": datos.MOTIVOS}
    if usuario and usuario["rol"] == "admin":
        contexto["reportes_pendientes"] = datos.contar_pendientes()
    return contexto


@bp.post("/crear")
@seguridad.requiere_login
def crear():
    siguiente = _ruta_local(request.form.get("siguiente"))
    if g.usuario["rol"] != "estudiante":
        abort(403)
    objeto_id = request.form.get("objeto_id", "")
    if not objeto_id.isdecimal():
        flash("No pudimos identificar el contenido a reportar.", "error")
        return redirect(siguiente)
    try:
        datos.crear_reporte(g.usuario["id"], request.form.get("tipo_objeto", ""), int(objeto_id),
                            (request.form.get("motivo") or "").strip())
    except datos.ErrorReporte as e:
        flash(str(e), "error")
    else:
        flash("Gracias por avisar. El equipo del Hub va a revisar tu reporte.")
    return redirect(siguiente)


@bp.get("/admin")
@seguridad.requiere_admin
def admin_cola():
    estado = request.args.get("estado", "pendiente")
    if estado not in ESTADOS:
        estado = "pendiente"
    grupos = datos.agrupar(datos.listar_reportes(estado))
    paginas = max(1, -(-len(grupos) // POR_PAGINA))
    pagina = min(max(request.args.get("pagina", 1, type=int) or 1, 1), paginas)
    return render_template(
        "reportes/admin_cola.html",
        grupos=grupos[(pagina - 1) * POR_PAGINA:pagina * POR_PAGINA],
        pagina=pagina,
        paginas=paginas,
        estado=estado,
        estados=ESTADOS,
        motivos=datos.MOTIVOS,
    )


@bp.post("/<int:reporte_id>/resolver")
@seguridad.requiere_admin
def resolver(reporte_id: int):
    if datos.obtener_reporte(reporte_id) is None:
        abort(404)
    accion = request.form.get("accion", "")
    try:
        resultado = datos.resolver_reporte(reporte_id, g.usuario["id"], accion, request.form.get("resolucion", ""))
    except datos.ErrorReporte as e:
        flash(str(e), "error")
        return redirect(url_for("reportes.admin_cola"))
    otros = resultado["resueltos"] - 1
    sufijo = f" También se cerraron {otros} reportes más sobre el mismo contenido." if otros > 0 else ""
    if accion == "bloquear":
        dueno = resultado["dueno_id"]
        if dueno and dueno != g.usuario["id"]:
            flash("Reporte derivado a bloqueo. Revisá la cuenta y bloqueala desde acá." + sufijo)
            return redirect(url_for("usuarios.ficha", usuario_id=dueno,
                                    motivo=(request.form.get("resolucion") or "").strip()))
        flash("Reporte derivado a bloqueo." + sufijo)
    elif accion == "ocultar":
        flash("Contenido ocultado: ya no lo ven los estudiantes." + sufijo)
    else:
        flash("Reporte descartado." + sufijo)
    return redirect(url_for("reportes.admin_cola"))


@bp.post("/<int:reporte_id>/restaurar")
@seguridad.requiere_admin
def restaurar(reporte_id: int):
    if datos.obtener_reporte(reporte_id) is None:
        abort(404)
    try:
        datos.restaurar_contenido(reporte_id, g.usuario["id"])
    except datos.ErrorReporte as e:
        flash(str(e), "error")
    else:
        flash("Contenido restaurado: vuelve a estar visible.")
    return redirect(url_for("reportes.admin_cola", estado="resuelto"))
