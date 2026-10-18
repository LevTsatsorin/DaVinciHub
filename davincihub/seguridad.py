from functools import wraps

from flask import abort, g, redirect, request, session, url_for

from davincihub import db


def cargar_usuario():
    g.usuario = None
    usuario_id = session.get("usuario_id")
    if usuario_id is None:
        return
    usuario = db.query_one("SELECT * FROM usuarios WHERE id = :id", id=usuario_id)
    if usuario is None:
        session.clear()
        return
    if usuario["bloqueado"]:
        session.clear()
        abort(403)
    g.usuario = usuario


def requiere_login(vista):
    @wraps(vista)
    def envoltura(**kwargs):
        if g.usuario is None:
            return redirect(url_for("auth.login", siguiente=request.path))
        return vista(**kwargs)

    return envoltura


def requiere_admin(vista):
    @wraps(vista)
    def envoltura(**kwargs):
        if g.usuario is None:
            return redirect(url_for("auth.login", siguiente=request.path))
        if g.usuario["rol"] != "admin":
            abort(403)
        return vista(**kwargs)

    return envoltura


def es_catedra(usuario_id: int, materia_id: int) -> bool:
    fila = db.query_one(
        "SELECT id FROM catedras WHERE usuario_id = :usuario AND materia_id = :materia",
        usuario=usuario_id,
        materia=materia_id,
    )
    return fila is not None
