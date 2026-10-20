from datetime import date, datetime

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from davincihub import seguridad
from davincihub.reservas import datos
from davincihub.utiles import ZONA_LOCAL

bp = Blueprint("reservas", __name__)
DIAS_CORTOS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")


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
            partes.extend(DIAS_CORTOS[dia] for dia in tramo)
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " y " + partes[-1]


@bp.app_template_filter("resumen_horarios")
def resumen_horarios(horarios: list[dict]) -> list[tuple[str, str]]:
    por_dia: dict[int, list[str]] = {}
    for horario in horarios:
        por_dia.setdefault(horario["dia_semana"], []).append(
            f"{horario['abre']}–{horario['cierra']}"
        )

    por_rango: dict[str, list[int]] = {}
    for dia in sorted(por_dia):
        por_rango.setdefault(", ".join(por_dia[dia]), []).append(dia)
    return [(_etiqueta_dias(dias), rango) for rango, dias in por_rango.items()]


def dia_actual() -> int:
    return datetime.now(ZONA_LOCAL).weekday()


@bp.app_template_filter("personas")
def personas(cantidad: int) -> str:
    numero = f"{cantidad:,}".replace(",", ".")
    return f"{numero} persona" if cantidad == 1 else f"{numero} personas"


def _minutos(hora: str) -> int:
    horas, minutos = hora.split(":")
    return int(horas) * 60 + int(minutos)


def _hora(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def _segmentos_disponibilidad(disponibilidad: dict) -> list[dict]:
    segmentos = []
    reservas = disponibilidad["reservas_ocupadas"]

    for horario in disponibilidad["horarios_habilitados"]:
        abre = _minutos(horario["abre"])
        cierra = _minutos(horario["cierra"])
        ocupadas = []
        for reserva in reservas:
            inicio_reserva = _minutos(reserva["inicio"][11:16])
            fin_reserva = _minutos(reserva["fin"][11:16])
            if inicio_reserva < cierra and fin_reserva > abre:
                ocupadas.append((max(abre, inicio_reserva), min(cierra, fin_reserva)))

        cursor = abre
        for inicio, fin in sorted(ocupadas):
            if inicio > cursor:
                segmentos.append({"tipo": "libre", "inicio": _hora(cursor), "fin": _hora(inicio)})
            if fin > cursor:
                segmentos.append({"tipo": "ocupado", "inicio": _hora(max(cursor, inicio)), "fin": _hora(fin)})
                cursor = fin
        if cursor < cierra:
            segmentos.append({"tipo": "libre", "inicio": _hora(cursor), "fin": _hora(cierra)})

    return segmentos


@bp.route("/espacios/")
@seguridad.requiere_login
def catalogo():
    es_admin = g.usuario["rol"] == "admin"
    espacios = datos.listar_espacios_admin() if es_admin else datos.listar_espacios_catalogo()
    hoy = dia_actual()
    abiertos_hoy = sum(
        1 for espacio in espacios if any(horario["dia_semana"] == hoy for horario in espacio["horarios"])
    )
    return render_template(
        "espacios/catalogo.html",
        espacios=espacios,
        abiertos_hoy=abiertos_hoy,
        dias=datos.DIAS_SEMANA,
        es_admin=es_admin,
    )


@bp.route("/espacios/<int:espacio_id>")
@seguridad.requiere_login
def detalle(espacio_id: int):
    espacio = datos.obtener_espacio(espacio_id)
    if espacio is None or (not espacio["activo"] and g.usuario["rol"] != "admin"):
        abort(404)

    fecha = request.args.get("fecha", date.today().isoformat())
    try:
        datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        flash("Elegí una fecha válida para consultar la disponibilidad.", "error")
        fecha = date.today().isoformat()

    disponibilidad = datos.obtener_disponibilidad_dia(espacio_id, fecha)
    return render_template(
        "espacios/detalle.html",
        espacio=espacio,
        fecha=fecha,
        hoy=date.today().isoformat(),
        disponibilidad=disponibilidad,
        segmentos=_segmentos_disponibilidad(disponibilidad),
        es_admin=g.usuario["rol"] == "admin",
    )


@bp.route("/espacios/<int:espacio_id>/reservar", methods=("POST",))
@seguridad.requiere_login
def reservar(espacio_id: int):
    fecha = request.form.get("fecha", "")
    inicio = request.form.get("inicio", "")
    fin = request.form.get("fin", "")
    try:
        if not fecha or not inicio or not fin:
            raise datos.ErrorHorarioInvalido("Completá la fecha, el inicio y el fin de la reserva.")
        reserva_id = datos.crear_reserva(
            espacio_id=espacio_id,
            usuario_id=g.usuario["id"],
            inicio=f"{fecha}T{inicio}",
            fin=f"{fecha}T{fin}",
        )
        flash("La reserva quedó confirmada.")
        return redirect(url_for("reservas.mis_reservas", reserva=reserva_id))
    except (datos.ErrorEspacio, datos.ErrorReserva) as error:
        flash(str(error), "error")
        return redirect(url_for("reservas.detalle", espacio_id=espacio_id, fecha=fecha or None))


@bp.route("/reservas/mis-reservas/")
@seguridad.requiere_login
def mis_reservas():
    reservas = datos.listar_reservas_usuario(g.usuario["id"], solo_futuras=True)
    return render_template("reservas/mis_reservas.html", reservas=reservas)


@bp.route("/reservas/<int:reserva_id>/cancelar", methods=("POST",))
@seguridad.requiere_login
def cancelar(reserva_id: int):
    try:
        datos.cancelar_reserva(reserva_id, usuario_id=g.usuario["id"])
        flash("La reserva fue cancelada y el horario quedó liberado.")
    except datos.ErrorReserva as error:
        flash(str(error), "error")
    return redirect(url_for("reservas.mis_reservas"))


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
    reservas_por_espacio: dict[int, list[dict]] = {espacio["id"]: [] for espacio in espacios}
    for reserva in datos.listar_todas_las_reservas():
        reservas_por_espacio.setdefault(reserva["espacio_id"], []).append(reserva)
    return render_template(
        "reservas/admin_todas.html",
        espacios=espacios,
        reservas_por_espacio=reservas_por_espacio,
    )