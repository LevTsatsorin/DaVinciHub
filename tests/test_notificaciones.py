import pytest

from davincihub import db
from davincihub.notificaciones import notificar


@pytest.fixture(autouse=True)
def sin_avisos_demo(app):
    with app.app_context():
        db.execute("DELETE FROM notificaciones")


def login(client, email="mica@davinci.edu.ar", password="davinci123"):
    return client.post("/auth/login", data={"email": email, "password": password})


def id_de(app, email):
    with app.app_context():
        return db.query_one("SELECT id FROM usuarios WHERE email = :email", email=email)["id"]


def avisar(app, email="mica@davinci.edu.ar", cuerpo="Tenés una nueva respuesta", enlace="/"):
    with app.app_context():
        return notificar(id_de(app, email), "foro", cuerpo, enlace)


def test_notificar_crea_aviso_no_leido(app):
    nuevo_id = avisar(app)
    with app.app_context():
        fila = db.query_one("SELECT * FROM notificaciones WHERE id = :id", id=nuevo_id)
    assert fila["leida"] == 0
    assert fila["tipo"] == "foro"
    assert fila["enlace"] == "/"


def test_notificar_rechaza_enlace_externo(app):
    with pytest.raises(ValueError):
        avisar(app, enlace="https://otro-sitio.com")
    with pytest.raises(ValueError):
        avisar(app, enlace="//otro-sitio.com")


def test_bandeja_requiere_login(client):
    respuesta = client.get("/notificaciones/")
    assert respuesta.status_code == 302
    assert "/auth/login" in respuesta.headers["Location"]


def test_bandeja_muestra_solo_avisos_propios(client, app):
    avisar(app, cuerpo="Aviso para Mica")
    avisar(app, email="tomas@davinci.edu.ar", cuerpo="Aviso para Tomás")
    login(client)
    texto = client.get("/notificaciones/").get_data(as_text=True)
    assert "Aviso para Mica" in texto
    assert "Aviso para Tomás" not in texto


def test_bandeja_vacia(client):
    login(client)
    texto = client.get("/notificaciones/").get_data(as_text=True)
    assert "No tenés avisos" in texto


def test_contador_en_la_barra(client, app):
    avisar(app)
    avisar(app)
    login(client)
    texto = client.get("/").get_data(as_text=True)
    assert 'data-avisos="2"' in texto


def test_abrir_aviso_lo_marca_leido_y_redirige(client, app):
    aviso = avisar(app, enlace="/auth/registro")
    login(client)
    respuesta = client.get(f"/notificaciones/{aviso}")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/auth/registro")
    with app.app_context():
        assert db.query_one("SELECT leida FROM notificaciones WHERE id = :id", id=aviso)["leida"] == 1


def test_aviso_ajeno_no_se_puede_abrir(client, app):
    ajeno = avisar(app, email="tomas@davinci.edu.ar")
    login(client)
    assert client.get(f"/notificaciones/{ajeno}").status_code == 404
    with app.app_context():
        assert db.query_one("SELECT leida FROM notificaciones WHERE id = :id", id=ajeno)["leida"] == 0


def test_marcar_todo_leido_solo_afecta_lo_propio(client, app):
    avisar(app)
    avisar(app)
    ajeno = avisar(app, email="tomas@davinci.edu.ar")
    login(client)
    respuesta = client.post("/notificaciones/leer-todas")
    assert respuesta.status_code == 302
    assert 'data-avisos="0"' in client.get("/").get_data(as_text=True)
    with app.app_context():
        assert db.query_one("SELECT leida FROM notificaciones WHERE id = :id", id=ajeno)["leida"] == 0
