import pytest

from davincihub import db
from davincihub.app import create_app


@pytest.fixture
def app(tmp_path):
    aplicacion = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "DATABASE_URL": f"sqlite:///{tmp_path}/test.db",
        }
    )
    with aplicacion.app_context():
        db.init_db(demo=True)
    return aplicacion


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def client_rutas(app):
    from davincihub import seguridad

    @app.route("/protegida")
    @seguridad.requiere_login
    def protegida():
        return "contenido protegido"

    @app.route("/solo-admin")
    @seguridad.requiere_admin
    def solo_admin():
        return "panel"

    return app.test_client()
