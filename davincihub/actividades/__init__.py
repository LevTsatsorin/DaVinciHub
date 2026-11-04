from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

from davincihub import seguridad
from davincihub.actividades.datos import (
    ErrorActividad,
    aprobar_actividad,
    cancelar_actividad,
    contar_actividades_por_estado,
    contar_actividades_publicas,
    crear_actividad,
    dar_de_baja,
    dias_con_actividades,
    esta_inscripto,
    inscribir,
    listar_actividades_admin,
    listar_actividades_creador,
    listar_actividades_publicas,
    listar_inscripciones_de,
    listar_inscriptos,
    obtener_actividad,
    rechazar_actividad,
)
from davincihub.reservas.datos import listar_espacios_catalogo, obtener_espacio
from davincihub.reservas.rutas import contexto_disponibilidad
from davincihub.utiles import ahora_local, hoy_local

bp = Blueprint("actividades", __name__, url_prefix="/actividades")

ESTADOS_MODERACION = {"pendiente": "Pendientes", "aprobada": "Aprobadas", "rechazada": "Rechazadas"}

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")

DIAS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")


@bp.app_template_filter("partes_fecha")
def partes_fecha(iso: str) -> dict:
    momento = datetime.fromisoformat(iso)
    return {"dia": DIAS[momento.weekday()], "numero": f"{momento.day:02d}", "mes": MESES[momento.month - 1][:3]}


POR_PAGINA = 10


def semanas_del_mes(anio: int, mes: int, cantidades: dict[str, int], hoy: str) -> list[list[dict]]:
    """Grilla del calendario: semanas de lunes a domingo que cubren el mes."""
    primero = date(anio, mes, 1)
    ultimo = _mes_siguiente(primero) - timedelta(days=1)
    inicio = primero - timedelta(days=primero.weekday())
    dias = [inicio + timedelta(days=n) for n in range((ultimo - inicio).days + 7 - ultimo.weekday())]
    celdas = [{"fecha": d.isoformat(), "numero": d.day, "en_mes": d.month == mes,
               "cantidad": cantidades.get(d.isoformat(), 0), "pasado": d.isoformat() < hoy,
               "hoy": d.isoformat() == hoy} for d in dias]
    return [celdas[n:n + 7] for n in range(0, len(celdas), 7)]


@bp.app_template_filter("duracion")
def duracion(act: dict) -> str:
    minutos = int((datetime.fromisoformat(act["fin"]) - datetime.fromisoformat(act["inicio"])).total_seconds() // 60)
    horas, resto = divmod(minutos, 60)
    return " ".join(p for p in (f"{horas} h" if horas else "", f"{resto} min" if resto else "") if p)


def _mes_pedido(valor: str | None, por_defecto: date) -> date:
    try:
        mes = datetime.strptime(valor or "", "%Y-%m").date()
    except ValueError:
        return por_defecto.replace(day=1)
    return mes if 2000 <= mes.year <= 2100 else por_defecto.replace(day=1)


def _dia_pedido(valor: str | None, mes: date) -> str:
    try:
        dia = date.fromisoformat(valor or "")
    except ValueError:
        return ""
    return dia.isoformat() if (dia.year, dia.month) == (mes.year, mes.month) else ""


def _mes_siguiente(mes: date) -> date:
    return (mes + timedelta(days=32)).replace(day=1)


@bp.route("/")
def index():
    """Listado público: la próxima actividad, el calendario del mes y el resto paginado."""
    hoy = date.fromisoformat(hoy_local())
    proximas = listar_actividades_publicas(limite=1)
    destacada = proximas[0] if proximas else None

    mes = _mes_pedido(request.args.get("mes"), date.fromisoformat(destacada["inicio"][:10]) if destacada else hoy)
    siguiente = _mes_siguiente(mes)
    dia = _dia_pedido(request.args.get("dia"), mes)
    desde, hasta = (dia, (date.fromisoformat(dia) + timedelta(days=1)).isoformat()) if dia \
        else (mes.isoformat(), siguiente.isoformat())
    excluir = None if dia or not destacada else destacada["id"]

    total = contar_actividades_publicas(desde, hasta, excluir)
    paginas = max(1, -(-total // POR_PAGINA))
    pagina = min(max(request.args.get("pagina", 1, type=int) or 1, 1), paginas)
    es_admin = g.usuario is not None and g.usuario["rol"] == "admin"
    return render_template(
        "actividades/index.html",
        destacada=destacada,
        actividades=listar_actividades_publicas(desde, hasta, POR_PAGINA, (pagina - 1) * POR_PAGINA, excluir),
        total=total,
        pagina=pagina,
        paginas=paginas,
        mes=mes,
        nombre_mes=f"{MESES[mes.month - 1].capitalize()} {mes.year}",
        mes_anterior=(mes - timedelta(days=1)).replace(day=1) if mes > hoy.replace(day=1) else None,
        mes_siguiente=siguiente,
        dia=dia,
        semanas=semanas_del_mes(mes.year, mes.month, dias_con_actividades(mes.isoformat(), siguiente.isoformat()),
                                hoy.isoformat()),
        pendientes=contar_actividades_por_estado().get("pendiente", 0) if es_admin else 0,
        ahora=ahora_local(),
    )


def _rol_en(actividad: dict) -> dict:
    usuario = g.get("usuario")
    return {
        "admin": bool(usuario) and usuario["rol"] == "admin",
        "creador": bool(usuario) and usuario["id"] == actividad["creador_id"],
        "inscripto": bool(usuario) and esta_inscripto(actividad["id"], usuario["id"]),
    }


@bp.route("/<int:actividad_id>")
def detalle(actividad_id: int):
    """Detalle de una actividad.

    RN-11 / CA-08: Sólo las actividades aprobadas son visibles para todos.
    Una pendiente o rechazada sólo la ven su creador y un admin; una cancelada, también sus inscriptos.
    """
    actividad = obtener_actividad(actividad_id)
    if not actividad:
        abort(404)
    rol = _rol_en(actividad)
    if actividad["oculto"] and not (rol["admin"] or rol["creador"]):
        abort(404)
    if actividad["estado"] != "aprobada" and not (
        rol["admin"] or rol["creador"] or (actividad["estado"] == "cancelada" and rol["inscripto"])
    ):
        abort(404)

    return render_template(
        "actividades/detalle.html",
        actividad=actividad,
        rol=rol,
        otras=listar_actividades_publicas(limite=3, excluir=actividad_id),
        ahora=ahora_local(),
    )


@bp.route("/<int:actividad_id>/inscriptos")
@seguridad.requiere_login
def inscriptos(actividad_id: int):
    """El creador (o un admin) ve quiénes se anotaron."""
    actividad = obtener_actividad(actividad_id)
    if not actividad:
        abort(404)
    rol = _rol_en(actividad)
    if not (rol["creador"] or rol["admin"]):
        abort(404)
    return render_template("actividades/inscriptos.html", actividad=actividad,
                           inscriptos=listar_inscriptos(actividad_id))


def _accion(actividad_id: int, funcion, mensaje: str):
    try:
        funcion(actividad_id, g.usuario["id"])
        flash(mensaje)
    except ErrorActividad as error:
        flash(str(error), "error")
    return redirect(url_for("actividades.detalle", actividad_id=actividad_id))


@bp.route("/<int:actividad_id>/inscribir", methods=("POST",))
@seguridad.requiere_login
def inscribirse(actividad_id: int):
    return _accion(actividad_id, inscribir, "¡Listo! Ya estás inscripto.")


@bp.route("/<int:actividad_id>/baja", methods=("POST",))
@seguridad.requiere_login
def baja(actividad_id: int):
    return _accion(actividad_id, dar_de_baja, "Te diste de baja: tu lugar quedó libre.")


@bp.route("/<int:actividad_id>/cancelar", methods=("POST",))
@seguridad.requiere_login
def cancelar(actividad_id: int):
    return _accion(actividad_id, cancelar_actividad, "La actividad fue cancelada y se avisó a los inscriptos.")


@bp.route("/crear")
@seguridad.requiere_login
def crear():
    """Propuesta de actividad: se elige espacio y día, y el horario en la línea de tiempo de reservas."""
    espacios = listar_espacios_catalogo()
    elegido = next((e for e in espacios if str(e["id"]) == request.args.get("espacio")), None)
    contexto = {"hoy": hoy_local(), "fecha": request.args.get("fecha")}
    if elegido:
        contexto = contexto_disponibilidad(obtener_espacio(elegido["id"]), request.args.get("fecha"))
    return render_template(
        "actividades/crear.html",
        espacios=espacios,
        elegido=elegido,
        formulario=session.pop("actividad_form", {}),
        **contexto,
    )


@bp.route("/crear", methods=("POST",))
@seguridad.requiere_login
def proponer():
    form = {campo: request.form.get(campo, "").strip()
            for campo in ("espacio_id", "fecha", "inicio", "fin", "nombre", "descripcion", "cupo_maximo")}
    try:
        if not form["espacio_id"].isdecimal() or not form["fecha"]:
            raise ErrorActividad("Elegí el espacio y el día de la actividad.")
        if not form["inicio"] or not form["fin"]:
            raise ErrorActividad("Elegí en la línea de tiempo el horario de la actividad.")
        if not form["cupo_maximo"].isascii() or not form["cupo_maximo"].isdecimal():
            raise ErrorActividad("El cupo máximo debe ser un número entero mayor a 0.")
        crear_actividad(
            creador_id=g.usuario["id"],
            nombre=form["nombre"],
            descripcion=form["descripcion"],
            espacio_id=int(form["espacio_id"]),
            inicio=f"{form['fecha']}T{form['inicio']}",
            fin=f"{form['fecha']}T{form['fin']}",
            cupo_maximo=int(form["cupo_maximo"]),
            aprobada=g.usuario["rol"] == "admin",
        )
    except ErrorActividad as error:
        flash(str(error), "error")
        session["actividad_form"] = form
        return redirect(url_for("actividades.crear", espacio=form["espacio_id"] or None, fecha=form["fecha"] or None))
    if g.usuario["rol"] == "admin":
        flash("Actividad publicada. El espacio quedó reservado.")
        return redirect(url_for("actividades.index"))
    flash("¡Actividad enviada! El espacio quedó reservado mientras la escuela la revisa.")
    return redirect(url_for("actividades.mis_actividades"))


@bp.route("/mis-actividades")
@seguridad.requiere_login
def mis_actividades():
    """Las actividades a las que se inscribió el estudiante y las que propuso, con su estado."""
    propuestas = listar_actividades_creador(g.usuario["id"])
    inscripciones = listar_inscripciones_de(g.usuario["id"])
    ver = request.args.get("ver") or ("propuestas" if propuestas and not inscripciones else "inscripciones")
    return render_template(
        "actividades/mis_actividades.html",
        ver="propuestas" if ver == "propuestas" else "inscripciones",
        actividades=propuestas,
        inscripciones=inscripciones,
        ahora=ahora_local(),
    )


@bp.route("/admin")
@seguridad.requiere_admin
def admin_panel():
    """Panel de administración para ver todas las actividades."""
    estado_filtro = request.args.get("estado")
    if estado_filtro not in ESTADOS_MODERACION:
        estado_filtro = None
    totales = contar_actividades_por_estado()
    total = totales.get(estado_filtro, 0) if estado_filtro else sum(totales.values())
    paginas = max(1, -(-total // POR_PAGINA))
    pagina = min(max(request.args.get("pagina", 1, type=int) or 1, 1), paginas)
    return render_template(
        "actividades/admin.html",
        actividades=listar_actividades_admin(estado_filtro, POR_PAGINA, (pagina - 1) * POR_PAGINA),
        estado_filtro=estado_filtro,
        pagina=pagina,
        paginas=paginas,
        totales=totales,
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
