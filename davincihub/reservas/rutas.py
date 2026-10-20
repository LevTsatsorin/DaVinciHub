from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from davincihub import db, seguridad
from davincihub.reservas import datos
from davincihub.utiles import ZONA_LOCAL

bp = Blueprint("espacios", __name__)

DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


@bp.app_template_filter("personas")
def personas(cantidad: int) -> str:
    numero = f"{cantidad:,}".replace(",", ".")
    return f"{numero} persona" if cantidad == 1 else f"{numero} personas"


def _etiqueta_dias(dias: list[int]) -> str:
    tramos: list[list[int]] = []
    for dia in dias:
        if tramos and tramos[-1][-1] == dia - 1:
            tramos[-1].append(dia)
        else:
            tramos.append([dia])
    partes = []
    for tramo in tramos:
        if len(tramo) >= 3:
            partes.append(f"{DIAS_CORTOS[tramo[0]]}–{DIAS_CORTOS[tramo[-1]]}")
        else:
            partes.extend(DIAS_CORTOS[d] for d in tramo)
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " y " + partes[-1]


@bp.app_template_filter("resumen_horarios")
def resumen_horarios(horarios: list[dict]) -> list[tuple[str, str]]:
    """Agrupa los días que comparten franjas: [("Lun–Vie", "09:00–21:00"), ...]."""
    por_dia: dict[int, list[str]] = {}
    for h in horarios:
        por_dia.setdefault(h["dia_semana"], []).append(f"{h['abre']}–{h['cierra']}")
    por_rango: dict[str, list[int]] = {}
    for dia in sorted(por_dia):
        por_rango.setdefault(", ".join(por_dia[dia]), []).append(dia)
    return [(_etiqueta_dias(dias), rango) for rango, dias in por_rango.items()]


def dia_actual() -> int:
    return datetime.now(ZONA_LOCAL).weekday()


@bp.route("/espacios/")
@seguridad.requiere_login
def catalogo():
    espacios = datos.listar_espacios_catalogo()
    hoy = dia_actual()
    abiertos_hoy = sum(1 for e in espacios if any(h["dia_semana"] == hoy for h in e["horarios"]))
    return render_template("espacios/catalogo.html", espacios=espacios, abiertos_hoy=abiertos_hoy,
                           dias=datos.DIAS_SEMANA)


@bp.route("/espacios/<int:espacio_id>")
@seguridad.requiere_login
def detalle(espacio_id: int):
    espacio = datos.obtener_espacio(espacio_id)
    if espacio is None or not espacio["activo"]:
        abort(404)
    return render_template("espacios/detalle.html", espacio=espacio, dias=datos.DIAS_SEMANA)


def _espacio_o_404(espacio_id: int) -> dict:
    espacio = datos.obtener_espacio(espacio_id)
    if espacio is None:
        abort(404)
    return espacio


def _franjas_del_formulario(form) -> list[dict]:
    dias, aperturas, cierres = form.getlist("dia_semana"), form.getlist("abre"), form.getlist("cierra")
    if not len(dias) == len(aperturas) == len(cierres):
        raise datos.ErrorFranjaHoraria("Las franjas enviadas están incompletas. Recargá la página.")
    franjas = []
    for dia, abre, cierra in zip(dias, aperturas, cierres, strict=True):
        abre, cierra = abre.strip(), cierra.strip()
        if not abre and not cierra:
            continue
        if not abre or not cierra:
            raise datos.ErrorFranjaHoraria(
                "Completá la hora de apertura y de cierre de cada franja."
            )
        franjas.append({"dia_semana": dia, "abre": abre, "cierra": cierra})
    return franjas


def _destino_interno(destino: str | None) -> str | None:
    if destino and destino.startswith("/") and not destino.startswith("//"):
        return destino
    return None


def _guardar(espacio_id: int | None, form) -> int:
    franjas = datos.validar_lista_franjas(_franjas_del_formulario(form))
    with db.transaccion():
        if espacio_id is None:
            espacio_id = datos.crear_espacio(
                form.get("nombre", ""), form.get("descripcion"), form.get("capacidad")
            )
        else:
            datos.actualizar_espacio(
                espacio_id, form.get("nombre", ""), form.get("descripcion"), form.get("capacidad")
            )
        datos.reemplazar_horarios_espacio(espacio_id, franjas)
    return espacio_id


def _franjas_para_mostrar(espacio: dict | None, form) -> list[dict]:
    if form:
        return [{"dia_semana": int(d) if d.isdecimal() else d, "abre": a, "cierra": c}
                for d, a, c in zip(form.getlist("dia_semana"), form.getlist("abre"),
                                   form.getlist("cierra"))]
    return espacio["horarios"] if espacio else []


def _formulario(espacio: dict | None):
    error = None
    if request.method == "POST":
        try:
            espacio_id = _guardar(espacio["id"] if espacio else None, request.form)
        except datos.ErrorEspacio as e:
            error = str(e)
        else:
            flash("Cambios guardados." if espacio else "Espacio creado.")
            return redirect(_destino_interno(request.form.get("siguiente"))
                            or url_for("espacios.admin_editar", espacio_id=espacio_id))
    return render_template(
        "espacios/admin_form.html",
        espacio=espacio,
        datos_form=request.form if request.method == "POST" else (espacio or {}),
        franjas=_franjas_para_mostrar(espacio, request.form if request.method == "POST" else None),
        error=error,
        dias=datos.DIAS_SEMANA,
    )


@bp.route("/admin/espacios/")
@seguridad.requiere_admin
def admin_lista():
    estado = "deshabilitados" if request.args.get("estado") == "deshabilitados" else "activos"
    todos = datos.listar_espacios_admin()
    activos = [e for e in todos if e["activo"]]
    apagados = [e for e in todos if not e["activo"]]
    return render_template(
        "espacios/admin_lista.html",
        estado=estado,
        espacios=apagados if estado == "deshabilitados" else activos,
        total_activos=len(activos),
        total_apagados=len(apagados),
        dias=datos.DIAS_SEMANA,
    )


@bp.route("/admin/espacios/nuevo", methods=("GET", "POST"))
@seguridad.requiere_admin
def admin_nuevo():
    return _formulario(None)


@bp.route("/admin/espacios/<int:espacio_id>/editar", methods=("GET", "POST"))
@seguridad.requiere_admin
def admin_editar(espacio_id: int):
    return _formulario(_espacio_o_404(espacio_id))


@bp.route("/admin/espacios/<int:espacio_id>/estado", methods=("POST",))
@seguridad.requiere_admin
def admin_estado(espacio_id: int):
    _espacio_o_404(espacio_id)
    activo = request.form.get("activo") == "1"
    datos.cambiar_estado_espacio(espacio_id, 1 if activo else 0)
    flash("Espacio habilitado." if activo else "Espacio deshabilitado: no admite reservas nuevas.")
    if request.form.get("volver") == "editar":
        return redirect(url_for("espacios.admin_editar", espacio_id=espacio_id))
    if activo:
        return redirect(url_for("espacios.admin_lista", estado="deshabilitados"))
    return redirect(url_for("espacios.admin_lista"))
