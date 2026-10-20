import os

# pyrefly: ignore[missing-import]
from flask import Flask, render_template
# pyrefly: ignore[missing-import]
from flask_wtf.csrf import CSRFProtect

from davincihub import auth, db, notificaciones, seguridad
from davincihub.actividades import rutas as actividades_rutas
from davincihub.reservas import rutas as reservas_rutas

csrf = CSRFProtect()


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    en_render = bool(os.environ.get("RENDER"))
    secreto = os.environ.get("SECRET_KEY")
    if en_render and not secreto:
        raise RuntimeError("Falta la variable de entorno SECRET_KEY.")
    app.config["SECRET_KEY"] = secreto or "dev"
    app.config["SESSION_COOKIE_SECURE"] = en_render
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["DATABASE_URL"] = os.environ.get("DATABASE_URL", "")
    if config:
        app.config.update(config)
    csrf.init_app(app)
    db.registrar(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(notificaciones.bp)
    app.register_blueprint(reservas_rutas.bp)
    app.register_blueprint(actividades_rutas.bp)
    app.before_request(seguridad.cargar_usuario)

    @app.route("/")
    def inicio():
        return render_template("inicio.html")

    @app.errorhandler(403)
    def prohibido(error):
        mensaje = "No tenés permiso para entrar acá."
        return render_template("error.html", codigo=403, mensaje=mensaje), 403

    @app.errorhandler(404)
    def no_encontrado(error):
        mensaje = "Esta página se perdió en el espacio."
        return render_template("error.html", codigo=404, mensaje=mensaje), 404

    return app
