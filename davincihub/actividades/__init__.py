from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

from davincihub import seguridad
from davincihub.actividades.datos import (
    ErrorActividad,
    aprobar_actividad,
    contar_actividades_por_estado,
    contar_actividades_publicas,
    crear_actividad,
    dias_con_actividades,
    listar_actividades_admin,
    listar_actividades_creador,
    listar_actividades_publicas,
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
        return datetime.strptime(valor or "", "%Y-%m").date()
    except ValueError:
        return por_defecto.replace(day=1)


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
    dia = request.args.get("dia", "")
    if not (dia[:7] == mes.isoformat()[:7] and len(dia) == 10):
        dia = ""
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

    return render_template(
        "actividades/detalle.html",
        actividad=actividad,
        otras=listar_actividades_publicas(limite=3, excluir=actividad_id),
        ahora=ahora_local(),
    )


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
