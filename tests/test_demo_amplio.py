import click
import pytest

from davincihub import db
from davincihub.demo_amplio import cargar


def test_datos_ampliados_se_cargan_una_vez_y_activan_las_coincidencias(app):
    with app.app_context():
        resumen = cargar()
        assert resumen["estudiantes"] > 30
        assert db.query_one("SELECT count(*) AS n FROM preguntas")["n"] > 30
        assert db.query_one("SELECT count(*) AS n FROM coincidencias")["n"] > 10
        bloqueado = db.query_one("SELECT id FROM usuarios WHERE email = 'ramiro@davinci.edu.ar' AND bloqueado = 1")
        assert db.query_one(
            "SELECT count(*) AS n FROM coincidencias c JOIN publicaciones p ON p.id = c.publicacion_id"
            " WHERE p.autor_id = :id", id=bloqueado["id"],
        )["n"] == 0
        with pytest.raises(click.ClickException):
            cargar()


def test_pantallas_principales_responden_con_datos_ampliados(app, client):
    with app.app_context():
        cargar()
    client.post("/auth/login", data={"email": "mica@davinci.edu.ar", "password": "davinci123"})
    for ruta in ("/", "/foro/", "/objetos/", "/objetos/busquedas", "/estudiantes/buscar",
                 "/estudiantes/2/conexiones", "/estudiantes/chats", "/actividades/", "/notificaciones/"):
        assert client.get(ruta).status_code == 200, ruta
