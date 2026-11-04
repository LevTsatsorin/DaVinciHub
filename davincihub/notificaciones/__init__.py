from flask import Blueprint, abort, g, jsonify, redirect, render_template, url_for

from davincihub import db, seguridad
from davincihub.utiles import ahora, fecha_corta

from . import feed

bp = Blueprint("notificaciones", __name__, url_prefix="/notificaciones")


def _es_interno(enlace: str) -> bool:
    return enlace.startswith("/") and not enlace.startswith("//")


def notificar(usuario_id: int, tipo: str, cuerpo: str, enlace: str | None = None) -> int:
    if enlace and not _es_interno(enlace):
        raise ValueError("El enlace de un aviso tiene que ser una ruta interna del sitio.")
    fila = db.query_one(
        "INSERT INTO notificaciones (usuario_id, tipo, cuerpo, enlace, creado)"
        " VALUES (:usuario, :tipo, :cuerpo, :enlace, :creado) RETURNING id",
        usuario=usuario_id,
        tipo=tipo,
        cuerpo=cuerpo,
        enlace=enlace,
        creado=ahora(),
    )
    return fila["id"]


def sin_leer(usuario_id: int) -> int:
    fila = db.query_one(
        "SELECT count(*) AS n FROM notificaciones WHERE usuario_id = :usuario AND leida = 0",
        usuario=usuario_id,
    )
    return fila["n"]


@bp.app_context_processor
def contador_de_avisos():
    usuario = g.get("usuario")
    return {"avisos_sin_leer": sin_leer(usuario["id"]) if usuario else 0}


@bp.app_template_filter("fecha_corta")
def filtro_fecha_corta(iso: str) -> str:
    return fecha_corta(iso)


@bp.route("/")
@seguridad.requiere_login
def bandeja():
    avisos = db.query(
        "SELECT * FROM notificaciones WHERE usuario_id = :usuario ORDER BY creado DESC, id DESC",
        usuario=g.usuario["id"],
    )
    return render_template(
        "notificaciones/bandeja.html",
        avisos=avisos,
        secciones=feed.agrupar(avisos, g.usuario["id"]),
        solicitudes=feed.solicitudes_pendientes(g.usuario["id"]) if g.usuario["rol"] == "estudiante" else [],
        tiempo_relativo=feed.tiempo_relativo,
    )


@bp.route("/<int:aviso_id>")
@seguridad.requiere_login
def abrir(aviso_id: int):
    aviso = db.query_one(
        "SELECT * FROM notificaciones WHERE id = :id AND usuario_id = :usuario",
        id=aviso_id,
        usuario=g.usuario["id"],
    )
    if aviso is None:
        abort(404)
    db.execute("UPDATE notificaciones SET leida = 1 WHERE id = :id", id=aviso_id)
    if aviso["enlace"]:
        db.execute(
            "UPDATE notificaciones SET leida = 1 WHERE usuario_id = :usuario AND tipo = :tipo"
            " AND enlace = :enlace AND leida = 0",
            usuario=g.usuario["id"], tipo=aviso["tipo"], enlace=aviso["enlace"],
        )
    enlace = aviso["enlace"]
    if not enlace or not _es_interno(enlace):
        enlace = url_for("notificaciones.bandeja")
    return redirect(enlace)


@bp.get("/contador")
@seguridad.requiere_login
def contador():
    return jsonify(avisos=sin_leer(g.usuario["id"]))


@bp.route("/leer-todas", methods=("POST",))
@seguridad.requiere_login
def leer_todas():
    db.execute(
        "UPDATE notificaciones SET leida = 1 WHERE usuario_id = :usuario AND leida = 0",
        usuario=g.usuario["id"],
    )
    return redirect(url_for("notificaciones.bandeja"))
