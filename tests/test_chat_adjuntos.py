import re
from io import BytesIO

import pytest

from davincihub import db


def ingresar(client, email="mica@davinci.edu.ar"):
    client.post("/auth/login", data={"email": email, "password": "davinci123"})


def enviar(client, nombre="apuntes.pdf", contenido=b"%PDF-1.4\nApuntes", cuerpo=""):
    return client.post("/estudiantes/3/chat", data={
        "cuerpo": cuerpo, "archivo": (BytesIO(contenido), nombre),
    }, headers={"X-Requested-With": "fetch"})


def test_archivo_sin_texto_es_privado_y_persistente(client, app):
    ingresar(client)
    respuesta = enviar(client)
    assert respuesta.status_code == 201
    mensaje = respuesta.json["mensaje"]
    assert "apuntes.pdf" in mensaje["extras"]
    url = f'/estudiantes/chat/mensajes/{mensaje["id"]}/archivo'
    descarga = client.get(url)
    assert descarga.data == b"%PDF-1.4\nApuntes"
    assert "attachment" in descarga.headers["Content-Disposition"]
    assert descarga.headers["Cache-Control"] == "private, no-store"
    assert "apuntes.pdf" in client.get("/estudiantes/3/chat").get_data(as_text=True)
    receptor = app.test_client()
    ingresar(receptor, "tomas@davinci.edu.ar")
    assert receptor.get(url).status_code == 200
    tercero = app.test_client()
    ingresar(tercero, "lucia@davinci.edu.ar")
    assert tercero.get(url).status_code == 404
    admin = app.test_client()
    ingresar(admin, "admin@davinci.edu.ar")
    assert admin.get(url).status_code == 403
    assert app.test_client().get(url).status_code == 302


@pytest.mark.parametrize(("nombre", "contenido"), [
    ("programa.exe", b"MZ"), ("falso.png", b"no es imagen"),
    ("falso.pdf", b"<script>alert(1)</script>"), ("vacio.txt", b""),
    ("falso.docx", b"PK mentira"), ("binario.txt", b"\x00\xff"),
])
def test_rechaza_archivos_invalidos_sin_crear_mensaje(client, app, nombre, contenido):
    ingresar(client)
    with app.app_context():
        antes = db.query_one("SELECT COUNT(*) AS n FROM mensajes")["n"]
    assert enviar(client, nombre, contenido).status_code == 400
    with app.app_context():
        assert db.query_one("SELECT COUNT(*) AS n FROM mensajes")["n"] == antes


def test_rechaza_archivo_grande_con_error_json(client):
    ingresar(client)
    respuesta = enviar(client, "grande.txt", b"a" * (10 * 1024 * 1024 + 1))
    assert respuesta.status_code == 400
    assert "10 MB" in respuesta.json["error"]


def test_limite_peticion_devuelve_json(client):
    ingresar(client)
    respuesta = enviar(client, "grande.txt", b"a" * (11 * 1024 * 1024))
    assert respuesta.status_code == 413
    assert respuesta.json["error"]


def test_imagen_con_texto_tiene_preview_y_descarga(client):
    ingresar(client)
    respuesta = enviar(client, "foto.png", b"\x89PNG\r\n\x1a\ncontenido", "Mi entrega")
    assert respuesta.status_code == 201
    mensaje = respuesta.json["mensaje"]
    assert mensaje["cuerpo"] == "Mi entrega"
    url = f'/estudiantes/chat/mensajes/{mensaje["id"]}/archivo?vista=1'
    vista = client.get(url)
    assert vista.mimetype == "image/png"
    assert "inline" in vista.headers["Content-Disposition"]
    assert "<img" in mensaje["extras"]


def test_reaccion_cambia_se_quita_y_se_actualiza_para_el_otro(client, app):
    ingresar(client)
    mensaje = enviar(client, "hola.txt", b"hola").json["mensaje"]
    url = f'/estudiantes/chat/mensajes/{mensaje["id"]}/reaccion'
    headers = {"X-Requested-With": "fetch"}
    assert client.post(url, data={"emoji": "👍"}, headers=headers).status_code == 200
    receptor = app.test_client()
    ingresar(receptor, "tomas@davinci.edu.ar")
    receptor.post(url, data={"emoji": "👍"}, headers=headers)
    actualizacion = receptor.get(f'/estudiantes/2/chat/nuevos?desde={mensaje["id"]}&visibles={mensaje["id"]}').json
    assert "👍 2" in actualizacion["extras"][str(mensaje["id"])]
    client.post(url, data={"emoji": "❤️"}, headers=headers)
    with app.app_context():
        assert db.query_one("SELECT emoji FROM reacciones_chat WHERE mensaje_id = :m AND usuario_id = 2", m=mensaje["id"])["emoji"] == "❤️"
    client.post(url, data={"emoji": "❤️"}, headers=headers)
    with app.app_context():
        assert db.query_one("SELECT * FROM reacciones_chat WHERE mensaje_id = :m AND usuario_id = 2", m=mensaje["id"]) is None
    assert client.post(url, data={"emoji": "invalido"}, headers=headers).status_code == 400
    tercero = app.test_client()
    ingresar(tercero, "lucia@davinci.edu.ar")
    assert tercero.post(url, data={"emoji": "👍"}, headers=headers).status_code == 404
    ajeno = tercero.get(f'/estudiantes/3/chat/nuevos?visibles={mensaje["id"]}').json
    assert str(mensaje["id"]) not in ajeno["extras"]


def test_migracion_agrega_tablas_sin_borrar_mensajes(client, app):
    ingresar(client)
    mensaje = enviar(client).json["mensaje"]
    with app.app_context():
        db.execute("DROP TABLE reacciones_chat")
        db.execute("DROP TABLE adjuntos_chat")
        db.migrar()
        db.migrar()
        assert db.query_one("SELECT id FROM mensajes WHERE id = :id", id=mensaje["id"])
        assert db.query("SELECT * FROM reacciones_chat") == []
        assert db.query("SELECT * FROM adjuntos_chat") == []


def test_nombre_adjunto_se_escapa_y_aparece_en_bandeja(client):
    ingresar(client)
    respuesta = enviar(client, '../../<img onerror=alert(1)>.txt', b"Apuntes")
    assert respuesta.status_code == 201
    extras = respuesta.json["mensaje"]["extras"]
    assert "&lt;img" in extras
    assert "<img onerror=" not in extras
    assert "../" not in extras
    assert "📎 &lt;img" in client.get("/estudiantes/chats").get_data(as_text=True)


def test_subidas_y_reacciones_requieren_csrf(client, app):
    ingresar(client)
    app.config["WTF_CSRF_ENABLED"] = True
    pagina = client.get("/estudiantes/3/chat").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', pagina).group(1)
    assert enviar(client).status_code == 400
    respuesta = client.post("/estudiantes/3/chat", data={
        "archivo": (BytesIO(b"Hola"), "hola.txt"), "csrf_token": token,
    }, headers={"X-Requested-With": "fetch"})
    assert respuesta.status_code == 201
    mensaje_id = respuesta.json["mensaje"]["id"]
    url = f"/estudiantes/chat/mensajes/{mensaje_id}/reaccion"
    assert client.post(url, data={"emoji": "👍"}).status_code == 400
    assert client.post(url, data={"emoji": "👍", "csrf_token": token}).status_code == 302
