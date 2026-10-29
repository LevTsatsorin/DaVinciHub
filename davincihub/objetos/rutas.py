from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from davincihub import seguridad
from davincihub.objetos import acuerdos, busquedas, datos, prestamos
from davincihub.utiles import hoy_local, paginas_visibles

bp = Blueprint("objetos", __name__, url_prefix="/objetos")


@bp.app_template_filter("fecha_prestamo")
def fecha_prestamo(valor):
    return date.fromisoformat(valor).strftime("%d/%m/%Y") if valor else "Sin fecha"


@bp.app_template_filter("precio_pesos")
def precio_pesos(valor) -> str:
    return "$" + f"{valor:,.2f}".translate(str.maketrans({",": ".", ".": ","}))


@bp.app_template_filter("precio_corto")
def precio_corto(valor) -> str:
    texto = precio_pesos(valor)
    return texto.removesuffix(",00")


@bp.context_processor
def opciones():
    return {
        "categorias": datos.CATEGORIAS, "condiciones": datos.CONDICIONES,
        "modalidades": datos.MODALIDADES, "estados": datos.ESTADOS,
        "modalidades_busqueda": busquedas.MODALIDADES,
        "categorias_busqueda": busquedas.CATEGORIAS,
        "estados_prestamo": prestamos.ESTADOS,
        "tipos_acuerdo": acuerdos.TIPOS,
        "estados_acuerdo": acuerdos.ESTADOS,
        "hoy": hoy_local(),
    }


def _solo_estudiante():
    if g.usuario["rol"] != "estudiante":
        abort(403)


def _publicacion(publicacion_id: int, propia: bool = False) -> dict:
    publicacion = datos.obtener(publicacion_id)
    if publicacion is None:
        abort(404)
    es_propia = publicacion["autor_id"] == g.usuario["id"]
    if propia and not es_propia:
        abort(403)
    if not es_propia and (publicacion["estado"] != "activa" or publicacion["autor_bloqueado"]):
        abort(404)
    if publicacion["oculto"] and not es_propia and g.usuario["rol"] != "admin":
        abort(404)
    return publicacion


def _filtros() -> dict:
    filtros = {"q": (request.args.get("q") or "").strip()[:120]}
    for campo, opciones_campo in (
        ("categoria", datos.CATEGORIAS), ("modalidad", datos.MODALIDADES),
        ("estado", datos.ESTADOS),
    ):
        valor = request.args.get(campo, "")
        filtros[campo] = valor if valor in opciones_campo else ""
    carrera = request.args.get("carrera_id", "")
    filtros["carrera_id"] = int(carrera) if carrera.isdecimal() and len(carrera) <= 9 else ""
    return filtros


def _listado(mias: bool = False):
    filtros = _filtros()
    if mias:
        filtros = {"q": "", "categoria": "", "modalidad": "", "carrera_id": "",
                   "estado": filtros["estado"]}
    else:
        filtros["estado"] = ""
        filtros["mostrar_mias"] = "1" if request.args.get("mostrar_mias") == "1" else ""
    try:
        pagina = int(request.args.get("pagina", "1")[:9])
    except ValueError:
        pagina = 1
    resultado = datos.listar(
        filtros, pagina, g.usuario["id"] if mias else None,
        excluir_autor_id=g.usuario["id"] if not mias and not filtros["mostrar_mias"] else None,
    )
    endpoint = "objetos.mis_publicaciones" if mias else "objetos.catalogo"
    enlaces = {
        "anterior": url_for(endpoint, **filtros, pagina=resultado["pagina"] - 1),
        "siguiente": url_for(endpoint, **filtros, pagina=resultado["pagina"] + 1),
        "paginas": [
            (numero, url_for(endpoint, **filtros, pagina=numero) if numero else None)
            for numero in paginas_visibles(resultado["pagina"], resultado["paginas"])
        ],
    }
    return render_template(
        "objetos/catalogo.html", **resultado, filtros=filtros, mias=mias,
        carreras=datos.carreras_disponibles(), enlaces=enlaces,
    )


@bp.get("/")
@seguridad.requiere_login
def catalogo():
    return _listado()


@bp.get("/mis-publicaciones")
@seguridad.requiere_login
def mis_publicaciones():
    _solo_estudiante()
    return _listado(mias=True)


@bp.get("/<int:publicacion_id>")
@seguridad.requiere_login
def detalle(publicacion_id: int):
    publicacion = _publicacion(publicacion_id)
    return render_template(
        "objetos/detalle.html", publicacion=publicacion,
        prestamo_abierto=prestamos.pendiente_propio(publicacion_id, g.usuario["id"]),
        objeto_ocupado=prestamos.ocupado(publicacion_id),
        acuerdo_abierto=acuerdos.abierta_propia(publicacion_id, g.usuario["id"]),
        acuerdo_reservado=acuerdos.reservada(publicacion_id),
    )


def _formulario(publicacion: dict | None = None):
    errores = {}
    if request.method == "POST":
        try:
            if publicacion:
                datos.editar(publicacion["id"], g.usuario["id"], request.form)
                publicacion_id = publicacion["id"]
            else:
                publicacion_id = datos.crear(g.usuario["id"], request.form)
        except datos.ErrorPublicacion as error:
            errores = error.errores
        except PermissionError:
            abort(403)
        except LookupError:
            abort(404)
        else:
            flash("Cambios guardados." if publicacion else "¡Tu publicación ya está en el catálogo!")
            return redirect(url_for("objetos.detalle", publicacion_id=publicacion_id))
    form = request.form if request.method == "POST" else (publicacion or {})
    return render_template(
        "objetos/formulario.html", publicacion=publicacion, datos_form=form, errores=errores,
        carreras=datos.carreras_disponibles(publicacion["carrera_id"] if publicacion else None),
    ), 400 if errores else 200


@bp.route("/publicar", methods=("GET", "POST"))
@seguridad.requiere_login
def publicar():
    _solo_estudiante()
    return _formulario()


@bp.route("/<int:publicacion_id>/editar", methods=("GET", "POST"))
@seguridad.requiere_login
def editar(publicacion_id: int):
    _solo_estudiante()
    publicacion = _publicacion(publicacion_id, propia=True)
    if publicacion["estado"] == "cerrada":
        return render_template(
            "error.html", codigo=409, mensaje="Una publicación cerrada ya no se puede editar."
        ), 409
    return _formulario(publicacion)


@bp.post("/<int:publicacion_id>/estado")
@seguridad.requiere_login
def estado(publicacion_id: int):
    _solo_estudiante()
    _publicacion(publicacion_id, propia=True)
    try:
        datos.cambiar_estado(publicacion_id, g.usuario["id"], request.form.get("estado", ""))
    except datos.ErrorPublicacion as error:
        return render_template("error.html", codigo=409, mensaje=str(error)), 409
    except PermissionError:
        abort(403)
    except LookupError:
        abort(404)
    flash("Estado de la publicación actualizado.")
    return redirect(url_for("objetos.detalle", publicacion_id=publicacion_id))


def _mi_busqueda(solicitud_id: int) -> dict:
    solicitud = busquedas.obtener(solicitud_id)
    if solicitud is None or solicitud["autor_id"] != g.usuario["id"]:
        abort(404)
    return solicitud


@bp.get("/busquedas")
@seguridad.requiere_login
def mis_busquedas():
    _solo_estudiante()
    try:
        pagina = int(request.args.get("pagina", "1")[:9])
    except ValueError:
        pagina = 1
    resultado = busquedas.listar_de(g.usuario["id"], request.args.get("estado", "activa"), pagina)
    return render_template("objetos/busquedas.html", **resultado)


@bp.route("/busquedas/nueva", methods=("GET", "POST"))
@seguridad.requiere_login
def nueva_busqueda():
    _solo_estudiante()
    errores = {}
    if request.method == "POST":
        try:
            solicitud_id, cantidad = busquedas.crear(g.usuario["id"], request.form)
        except busquedas.ErrorBusqueda as error:
            errores = error.errores
        except PermissionError:
            abort(403)
        else:
            if cantidad:
                resultado = "una posible coincidencia" if cantidad == 1 else f"{cantidad} posibles coincidencias"
                flash(f"Búsqueda creada. Encontramos {resultado}.")
            else:
                flash("Búsqueda creada. Te avisaremos cuando aparezca un objeto compatible.")
            return redirect(url_for("objetos.detalle_busqueda", solicitud_id=solicitud_id))
    return render_template(
        "objetos/busqueda_formulario.html", errores=errores, datos_form=request.form,
    ), 400 if errores else 200


@bp.get("/busquedas/<int:solicitud_id>")
@seguridad.requiere_login
def detalle_busqueda(solicitud_id: int):
    _solo_estudiante()
    solicitud = _mi_busqueda(solicitud_id)
    return render_template("objetos/busqueda_detalle.html", solicitud=solicitud,
                           publicaciones=busquedas.coincidencias_de(solicitud), mias=False)


@bp.post("/busquedas/<int:solicitud_id>/cerrar")
@seguridad.requiere_login
def cerrar_busqueda(solicitud_id: int):
    _solo_estudiante()
    _mi_busqueda(solicitud_id)
    try:
        busquedas.cerrar(solicitud_id, g.usuario["id"])
    except PermissionError:
        abort(403)
    except LookupError:
        abort(404)
    flash("Búsqueda cerrada. Ya no generará nuevas coincidencias ni avisos.")
    return redirect(url_for("objetos.detalle_busqueda", solicitud_id=solicitud_id))


def _mi_prestamo(prestamo_id):
    _solo_estudiante()
    prestamo = prestamos.obtener(prestamo_id)
    if prestamo is None or g.usuario["id"] not in (prestamo["propietario_id"], prestamo["solicitante_id"]):
        abort(404)
    return prestamo


@bp.get("/prestamos")
@seguridad.requiere_login
def mis_prestamos():
    _solo_estudiante()
    try:
        pagina = int(request.args.get("pagina", "1")[:9])
    except ValueError:
        pagina = 1
    resultado = prestamos.listar(
        g.usuario["id"], request.args.get("vista", "pedidos"), request.args.get("estado", ""), pagina,
    )
    return render_template("objetos/prestamos.html", **resultado)


@bp.route("/<int:publicacion_id>/solicitar-prestamo", methods=("GET", "POST"))
@seguridad.requiere_login
def solicitar_prestamo(publicacion_id):
    _solo_estudiante()
    publicacion = _publicacion(publicacion_id)
    if publicacion["autor_id"] == g.usuario["id"]:
        abort(403)
    if publicacion["modalidad"] != "prestamo":
        return render_template("error.html", codigo=409, mensaje="Esta publicación no ofrece préstamos."), 409
    errores = {}
    if request.method == "POST":
        try:
            prestamo_id = prestamos.solicitar(publicacion_id, g.usuario["id"], request.form)
        except prestamos.ErrorPrestamo as error:
            errores = error.errores
        except PermissionError:
            abort(403)
        except LookupError:
            abort(404)
        else:
            flash("Solicitud enviada. Te avisaremos cuando el propietario responda.")
            return redirect(url_for("objetos.detalle_prestamo", prestamo_id=prestamo_id))
    abierto = prestamos.pendiente_propio(publicacion_id, g.usuario["id"])
    if request.method == "GET" and abierto:
        return redirect(url_for("objetos.detalle_prestamo", prestamo_id=abierto["id"]))
    return render_template(
        "objetos/prestamo_formulario.html", publicacion=publicacion, errores=errores,
        datos_form=request.form, objeto_ocupado=prestamos.ocupado(publicacion_id),
    ), 400 if errores else 200


@bp.get("/prestamos/<int:prestamo_id>")
@seguridad.requiere_login
def detalle_prestamo(prestamo_id):
    prestamo = _mi_prestamo(prestamo_id)
    return _detalle_prestamo(prestamo)


def _detalle_prestamo(prestamo, errores=None):
    return render_template(
        "objetos/prestamo_detalle.html", prestamo=prestamo,
        movimientos=prestamos.movimientos(prestamo["id"]), errores=errores or {},
        acciones=prestamos.acciones(prestamo, g.usuario["id"]),
        datos_form=request.form if errores else prestamo,
    )


@bp.post("/prestamos/<int:prestamo_id>/accion")
@seguridad.requiere_login
def accion_prestamo(prestamo_id):
    prestamo = _mi_prestamo(prestamo_id)
    try:
        prestamos.cambiar(prestamo_id, g.usuario["id"], request.form.get("accion", ""), request.form)
    except prestamos.ErrorPrestamo as error:
        return _detalle_prestamo(prestamos.obtener(prestamo_id), error.errores), 409 if "general" in error.errores else 400
    except PermissionError:
        abort(403)
    except LookupError:
        abort(404)
    flash("Préstamo actualizado.")
    return redirect(url_for("objetos.detalle_prestamo", prestamo_id=prestamo["id"]))


def _mi_acuerdo(tipo, acuerdo_id):
    _solo_estudiante()
    try:
        acuerdo = acuerdos.obtener(tipo, acuerdo_id)
    except LookupError:
        abort(404)
    if acuerdo is None or g.usuario["id"] not in (acuerdo["propietario_id"], acuerdo["solicitante_id"]):
        abort(404)
    return acuerdo


@bp.get("/acuerdos")
@seguridad.requiere_login
def mis_acuerdos():
    _solo_estudiante()
    try:
        pagina = int(request.args.get("pagina", "1")[:9])
    except ValueError:
        pagina = 1
    resultado = acuerdos.listar(g.usuario["id"], request.args.get("vista", "enviadas"),
                               request.args.get("tipo", ""), request.args.get("estado", ""), pagina)
    return render_template("objetos/acuerdos.html", **resultado)


@bp.route("/<int:publicacion_id>/proponer", methods=("GET", "POST"))
@seguridad.requiere_login
def proponer_acuerdo(publicacion_id):
    _solo_estudiante()
    publicacion = _publicacion(publicacion_id)
    if publicacion["autor_id"] == g.usuario["id"]:
        abort(403)
    if publicacion["modalidad"] not in acuerdos.TIPOS:
        return render_template("error.html", codigo=409, mensaje="Esta publicación ofrece un préstamo. Usá Pedir prestado."), 409
    errores = {}
    if request.method == "POST":
        try:
            tipo, acuerdo_id = acuerdos.proponer(publicacion_id, g.usuario["id"], request.form)
        except acuerdos.ErrorAcuerdo as error:
            errores = error.errores
        except PermissionError:
            abort(403)
        except LookupError:
            abort(404)
        else:
            flash("Propuesta enviada. Te avisaremos cuando el propietario responda.")
            return redirect(url_for("objetos.detalle_acuerdo", tipo=tipo, acuerdo_id=acuerdo_id))
    abierta = acuerdos.abierta_propia(publicacion_id, g.usuario["id"])
    if request.method == "GET" and abierta:
        return redirect(url_for("objetos.detalle_acuerdo", tipo=abierta["tipo"], acuerdo_id=abierta["id"]))
    inicial = {"precio_acordado": publicacion["precio"]} if publicacion["modalidad"] == "venta" else {}
    return render_template(
        "objetos/acuerdo_formulario.html", publicacion=publicacion, errores=errores,
        datos_form=request.form if request.method == "POST" else inicial,
        ofrecibles=acuerdos.ofrecibles(g.usuario["id"]), acuerdo_reservado=acuerdos.reservada(publicacion_id),
    ), 400 if errores else 200


def _detalle_acuerdo(acuerdo, errores=None):
    return render_template("objetos/acuerdo_detalle.html", acuerdo=acuerdo, errores=errores or {},
                           movimientos=acuerdos.movimientos(acuerdo["tipo"], acuerdo["id"]),
                           acciones=acuerdos.acciones(acuerdo, g.usuario["id"]))


@bp.get("/acuerdos/<tipo>/<int:acuerdo_id>")
@seguridad.requiere_login
def detalle_acuerdo(tipo, acuerdo_id):
    return _detalle_acuerdo(_mi_acuerdo(tipo, acuerdo_id))


@bp.post("/acuerdos/<tipo>/<int:acuerdo_id>/accion")
@seguridad.requiere_login
def accion_acuerdo(tipo, acuerdo_id):
    _mi_acuerdo(tipo, acuerdo_id)
    try:
        acuerdos.cambiar(tipo, acuerdo_id, g.usuario["id"], request.form.get("accion", ""))
    except acuerdos.ErrorAcuerdo as error:
        return _detalle_acuerdo(acuerdos.obtener(tipo, acuerdo_id), error.errores), 409
    except PermissionError:
        abort(403)
    except LookupError:
        abort(404)
    flash("Acuerdo actualizado.")
    return redirect(url_for("objetos.detalle_acuerdo", tipo=tipo, acuerdo_id=acuerdo_id))
