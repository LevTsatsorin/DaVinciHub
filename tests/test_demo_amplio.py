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
        assert resumen["reportes"] == 7
        assert db.query_one("SELECT count(*) AS n FROM reportes WHERE estado = 'pendiente'")["n"] == 4
        joaco = db.query_one("SELECT id FROM usuarios WHERE email = 'joaco@davinci.edu.ar'")["id"]
        ids = [f["id"] for f in db.query(
            "SELECT id FROM mensajes WHERE (emisor_id = 2 AND receptor_id = :j) OR (emisor_id = :j AND receptor_id = 2)"
            " ORDER BY creado", j=joaco)]
        assert len(ids) > 100 and ids == sorted(ids)
        with pytest.raises(click.ClickException):
            cargar()


def test_sobre_una_base_ampliada_vieja_solo_suma_lo_nuevo(app):
    from davincihub.demo_amplio import _chats_largos, _reportes

    with app.app_context():
        cargar()
        db.execute("DELETE FROM reportes")
        db.execute("UPDATE publicaciones SET oculto = 0")
        usuarios = db.query_one("SELECT count(*) AS n FROM usuarios")["n"]
        resumen = cargar()
        assert set(resumen) == {"mensajes en chats largos", "reportes"}
        assert db.query_one("SELECT count(*) AS n FROM usuarios")["n"] == usuarios
        assert callable(_chats_largos) and callable(_reportes)


def test_pantallas_principales_responden_con_datos_ampliados(app, client):
    with app.app_context():
        cargar()
    client.post("/auth/login", data={"email": "mica@davinci.edu.ar", "password": "davinci123"})
    for ruta in ("/", "/foro/", "/objetos/", "/objetos/busquedas", "/estudiantes/buscar",
                 "/estudiantes/2/conexiones", "/estudiantes/chats", "/actividades/", "/notificaciones/"):
        assert client.get(ruta).status_code == 200, ruta
