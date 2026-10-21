from functools import wraps

from flask import abort, g, redirect, render_template, request, session, url_for

from davincihub import db


def cargar_usuario():
    g.usuario = None
    usuario_id = session.get("usuario_id")
    if usuario_id is None:
        return
    usuario = db.query_one(
        "SELECT u.*, CASE WHEN EXISTS (SELECT 1 FROM fotos_perfil f"
        " WHERE f.usuario_id = u.id) THEN 1 ELSE 0 END AS tiene_foto"
        " FROM usuarios u WHERE u.id = :id",
        id=usuario_id,
    )
    if usuario is None:
        session.clear()
        return
    if usuario["bloqueado"]:
        session.clear()
        mensaje = "Tu cuenta está bloqueada. Si creés que es un error, escribí a la escuela."
        return render_template("error.html", codigo=403, mensaje=mensaje), 403
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
    """De cátedra en una materia: tiene el rol y ya cursó esa materia de su carrera."""
    fila = db.query_one(
        "SELECT u.id FROM usuarios u JOIN materias m ON m.carrera_id = u.carrera_id"
        " WHERE u.id = :usuario AND m.id = :materia AND u.catedra = 1 AND u.rol = 'estudiante'"
        " AND m.cuatrimestre <= (coalesce(u.anio, 1) - 1) * 2",
        usuario=usuario_id,
        materia=materia_id,
    )
    return fila is not None
