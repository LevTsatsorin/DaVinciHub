from datetime import UTC, datetime

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from davincihub import db, seguridad, validacion

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _ahora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@bp.route("/registro", methods=("GET", "POST"))
def registro():
    errores = {}
    if request.method == "POST":
        errores = validacion.validar_registro(request.form)
        email = (request.form.get("email") or "").strip().lower()
        if not errores and db.query_one(
            "SELECT id FROM usuarios WHERE email = :email", email=email
        ):
            errores["email"] = "Ese email ya está registrado."
        if not errores:
            try:
                fila = db.query_one(
                    "INSERT INTO usuarios (nombre, apellido, email, password_hash, creado)"
                    " VALUES (:nombre, :apellido, :email, :hash, :creado) RETURNING id",
                    nombre=request.form["nombre"].strip(),
                    apellido=request.form["apellido"].strip(),
                    email=email,
                    hash=generate_password_hash(request.form["password"]),
                    creado=_ahora(),
                )
            except db.ErrorIntegridad:
                errores["email"] = "Ese email ya está registrado."
            else:
                session.clear()
                session["usuario_id"] = fila["id"]
                return redirect(url_for("auth.registro_datos"))
    return render_template("auth/registro.html", errores=errores, datos=request.form)


@bp.route("/registro/datos", methods=("GET", "POST"))
@seguridad.requiere_login
def registro_datos():
    errores = {}
    if request.method == "POST":
        errores = validacion.validar_datos_estudiante(request.form)
        if not errores and not db.query_one(
            "SELECT id FROM carreras WHERE id = :id AND activa = 1",
            id=int(request.form["carrera_id"]),
        ):
            errores["carrera_id"] = "Elegí una carrera válida."
        if not errores:
            db.execute(
                "UPDATE usuarios SET carrera_id = :carrera, anio = :anio, comision = :comision"
                " WHERE id = :id",
                carrera=int(request.form["carrera_id"]),
                anio=int(request.form["anio"]),
                comision=request.form["comision"].strip(),
                id=g.usuario["id"],
            )
            flash("¡Listo! Tu cuenta quedó completa.")
            return redirect(url_for("inicio"))
    carreras = db.query("SELECT id, nombre FROM carreras WHERE activa = 1 ORDER BY nombre")
    return render_template(
        "auth/registro_datos.html", errores=errores, carreras=carreras, datos=request.form
    )


@bp.route("/login", methods=("GET", "POST"))
def login():
    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        usuario = db.query_one("SELECT * FROM usuarios WHERE email = :email", email=email)
        if usuario is None or not check_password_hash(usuario["password_hash"], password):
            error = "Email o contraseña incorrectos."
        elif usuario["bloqueado"]:
            error = "La cuenta está bloqueada."
        else:
            session.clear()
            session["usuario_id"] = usuario["id"]
            return redirect(url_for("inicio"))
    return render_template("auth/login.html", error=error)


@bp.route("/salir", methods=("POST",))
def salir():
    session.clear()
    return redirect(url_for("inicio"))
