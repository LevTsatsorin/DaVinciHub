from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from davincihub import seguridad
from davincihub.objetos import busquedas, datos
from davincihub.utiles import paginas_visibles

bp = Blueprint("objetos", __name__, url_prefix="/objetos")


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
    return render_template("objetos/detalle.html", publicacion=_publicacion(publicacion_id))


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
