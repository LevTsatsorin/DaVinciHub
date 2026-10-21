import unicodedata
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

from davincihub import db, seguridad
from davincihub.reservas import datos
from davincihub.utiles import ZONA_LOCAL, ahora_local, hoy_local

bp = Blueprint("espacios", __name__)

MINUTOS_TURNO = 30
DIAS_PANEL = 7
LIMITE_HISTORIAL = 10
DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


@bp.app_template_filter("dia_y_fecha")
def dia_y_fecha(iso: str) -> str:
    momento = datetime.fromisoformat(iso)
    return f"{DIAS_CORTOS[momento.weekday()]} {momento:%d/%m}"


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


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.casefold()) if not unicodedata.combining(c))


def _filtros_catalogo(args) -> dict:
    fecha = args.get("fecha", "")
    try:
        fecha = date.fromisoformat(fecha).isoformat()
    except ValueError:
        fecha = ""
    personas = args.get("personas", "")
    return {
        "q": args.get("q", "").strip(),
        "fecha": fecha,
        "personas": int(personas) if personas.isascii() and personas.isdecimal() and int(personas) > 0 else None,
    }


@bp.route("/espacios/")
@seguridad.requiere_login
def catalogo():
    todos = datos.listar_espacios_catalogo()
    hoy = dia_actual()
    abiertos_hoy = sum(1 for e in todos if any(h["dia_semana"] == hoy for h in e["horarios"]))
    filtros = _filtros_catalogo(request.args)
    espacios = [
        e for e in todos
        if _sin_acentos(filtros["q"]) in _sin_acentos(e["nombre"])
        and (not filtros["personas"] or not e["capacidad"] or e["capacidad"] >= filtros["personas"])
    ]
    if filtros["fecha"]:
        ahora = ahora_local()
        for e in espacios:
            e["libres"] = rangos_libres(turnos_del_dia(datos.obtener_disponibilidad_dia(e["id"], filtros["fecha"], e), ahora))
        espacios = [e for e in espacios if e["libres"]]
    return render_template(
        "espacios/catalogo.html",
        espacios=espacios,
        total=len(todos),
        abiertos_hoy=abiertos_hoy,
        filtros=filtros,
        hoy=hoy_local(),
        dias=datos.DIAS_SEMANA,
    )


def _minutos(hora: str) -> int:
    horas, minutos = hora.split(":")
    return int(horas) * 60 + int(minutos)


def _hora(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def turnos_del_dia(disponibilidad: dict, ahora: str) -> list[dict]:
    fecha = disponibilidad["fecha"]
    ocupadas = [(r["inicio"][11:16], r["fin"][11:16]) for r in disponibilidad["reservas_ocupadas"]]
    bloques = []
    for horario in sorted(disponibilidad["horarios_habilitados"], key=lambda h: h["abre"]):
        cierra = _minutos(horario["cierra"])
        turnos = []
        for minuto in range(_minutos(horario["abre"]), cierra, MINUTOS_TURNO):
            inicio, fin = _hora(minuto), _hora(min(minuto + MINUTOS_TURNO, cierra))
            if f"{fecha}T{inicio}" < ahora[:16]:
                estado = "pasado"
            elif any(inicio < o_fin and fin > o_ini for o_ini, o_fin in ocupadas):
                estado = "ocupado"
            else:
                estado = "libre"
            turnos.append({"inicio": inicio, "fin": fin, "estado": estado})
        bloques.append({"abre": horario["abre"], "cierra": horario["cierra"], "turnos": turnos})
    return bloques


def rangos_libres(bloques: list[dict]) -> list[tuple[str, str]]:
    """Une los turnos libres seguidos en rangos: [("09:00", "10:00"), ("11:00", "13:00")]."""
    rangos: list[list[str]] = []
    for bloque in bloques:
        for turno in bloque["turnos"]:
            if turno["estado"] != "libre":
                continue
            if rangos and rangos[-1][1] == turno["inicio"]:
                rangos[-1][1] = turno["fin"]
            else:
                rangos.append([turno["inicio"], turno["fin"]])
    return [(inicio, fin) for inicio, fin in rangos]


def proximos_dias(desde: str, horarios: list[dict], cantidad: int = DIAS_PANEL) -> list[dict]:
    abiertos = {h["dia_semana"] for h in horarios}
    inicio = date.fromisoformat(desde)
    dias = []
    for salto in range(cantidad):
        dia = inicio + timedelta(days=salto)
        dias.append({
            "fecha": dia.isoformat(),
            "etiqueta": DIAS_CORTOS[dia.weekday()],
            "numero": f"{dia.day:02d}",
            "abierto": dia.weekday() in abiertos,
        })
    return dias


def _ayer(fecha: str) -> str:
    return (date.fromisoformat(fecha) - timedelta(days=1)).isoformat()


def _siguiente_dia_abierto(desde: str, horarios: list[dict]) -> str | None:
    siguiente = (date.fromisoformat(desde) + timedelta(days=1)).isoformat()
    return next((d["fecha"] for d in proximos_dias(siguiente, horarios, 7) if d["abierto"]), None)


def contexto_disponibilidad(espacio: dict, fecha: str | None) -> dict:
    """Datos de la línea de tiempo de un día: la usan la reserva y la propuesta de actividades."""
    hoy = hoy_local()
    try:
        fecha = datetime.strptime(fecha or hoy, "%Y-%m-%d").date().isoformat()
    except ValueError:
        flash("Elegí una fecha válida para consultar la disponibilidad.", "error")
        fecha = hoy
    disponibilidad = datos.obtener_disponibilidad_dia(espacio["id"], fecha, espacio)
    bloques = turnos_del_dia(disponibilidad, ahora_local())
    return {
        "espacio": espacio,
        "fecha": fecha,
        "hoy": hoy,
        "disponibilidad": disponibilidad,
        "bloques": bloques,
        "hay_libres": any(t["estado"] == "libre" for b in bloques for t in b["turnos"]),
        "proximos": proximos_dias(hoy, espacio["horarios"]),
        "siguiente_abierto": _siguiente_dia_abierto(max(fecha, _ayer(hoy)), espacio["horarios"]),
        "es_pasado": fecha < hoy,
    }


@bp.route("/espacios/<int:espacio_id>")
@seguridad.requiere_login
def detalle(espacio_id: int):
    espacio = datos.obtener_espacio(espacio_id)
    if espacio is None or (not espacio["activo"] and g.usuario["rol"] != "admin"):
        abort(404)

    return render_template(
        "espacios/detalle.html",
        **contexto_disponibilidad(espacio, request.args.get("fecha")),
        formulario=session.pop("reserva_form", {}),
        es_admin=g.usuario["rol"] == "admin",
        dias=datos.DIAS_SEMANA,
        limite_motivo=datos.LIMITE_MOTIVO,
    )


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


@bp.route("/espacios/<int:espacio_id>/reservar", methods=("POST",))
@seguridad.requiere_login
def reservar(espacio_id: int):
    fecha = request.form.get("fecha", "")
    inicio = request.form.get("inicio", "")
    fin = request.form.get("fin", "")
    motivo = request.form.get("motivo", "").strip()
    personas = request.form.get("personas", "").strip()
    try:
        if not fecha or not inicio or not fin:
            raise datos.ErrorHorarioInvalido("Elegí en la grilla el horario que querés reservar.")
        if not motivo:
            raise datos.ErrorReserva("Contá para qué vas a usar el espacio.")
        if not personas.isdecimal() or int(personas) < 1:
            raise datos.ErrorReserva("Indicá cuántas personas van a usar el espacio.")
        reserva_id = datos.crear_reserva(
            espacio_id=espacio_id,
            usuario_id=g.usuario["id"],
            inicio=f"{fecha}T{inicio}",
            fin=f"{fecha}T{fin}",
            motivo=motivo,
            personas=int(personas),
        )
        return redirect(url_for("espacios.mis_reservas", reserva=reserva_id))
    except (datos.ErrorEspacio, datos.ErrorReserva) as error:
        flash(str(error), "error")
        session["reserva_form"] = {"inicio": inicio, "fin": fin, "motivo": motivo, "personas": personas}
        return redirect(url_for("espacios.detalle", espacio_id=espacio_id, fecha=fecha or None))


@bp.route("/reservas/mis-reservas/")
@seguridad.requiere_login
def mis_reservas():
    reservas = datos.listar_reservas_usuario(g.usuario["id"], solo_futuras=True)
    historial = datos.listar_historial_usuario(g.usuario["id"], LIMITE_HISTORIAL)
    nueva = request.args.get("reserva", type=int)
    return render_template("reservas/mis_reservas.html", reservas=reservas, historial=historial, nueva=nueva)


@bp.route("/reservas/<int:reserva_id>/cancelar", methods=("POST",))
@seguridad.requiere_login
def cancelar(reserva_id: int):
    try:
        datos.cancelar_reserva(reserva_id, usuario_id=g.usuario["id"])
        flash("La reserva fue cancelada y el horario quedó liberado.")
    except datos.ErrorReserva as error:
        flash(str(error), "error")
    return redirect(url_for("espacios.mis_reservas"))


@bp.route("/admin/espacios/<int:espacio_id>/reservas/")
@seguridad.requiere_admin
def reservas_admin(espacio_id: int):
    espacio = datos.obtener_espacio(espacio_id, incluir_horarios=False)
    if espacio is None:
        abort(404)
    reservas = datos.listar_todas_las_reservas(espacio_id)
    return render_template("espacios/reservas_admin.html", espacio=espacio, reservas=reservas)


@bp.route("/admin/reservas/")
@seguridad.requiere_admin
def reservas_admin_todas():
    espacios = datos.listar_espacios_admin()
    reservas_por_espacio: dict[int, list[dict]] = {}
    for reserva in datos.listar_todas_las_reservas():
        reservas_por_espacio.setdefault(reserva["espacio_id"], []).append(reserva)
    return render_template(
        "reservas/admin_todas.html",
        con_reservas=[e for e in espacios if e["id"] in reservas_por_espacio],
        reservas_por_espacio=reservas_por_espacio,
    )
