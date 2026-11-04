import pytest

from davincihub import db

FETCH = {"X-Requested-With": "fetch"}


@pytest.fixture(autouse=True)
def sin_mensajes(app):
    with app.app_context():
        db.execute("DELETE FROM mensajes")
        db.execute("DELETE FROM notificaciones")


def ingresar(client, email="mica@davinci.edu.ar"):
    client.post("/auth/login", data={"email": email, "password": "davinci123"})
    return client


def test_enviar_por_fetch_devuelve_el_mensaje_sin_recargar(client):
    ingresar(client)
    respuesta = client.post("/estudiantes/3/chat", data={"cuerpo": "  Hola <b>Tomás</b>\r\n¿vamos?  "}, headers=FETCH)
    assert respuesta.status_code == 201
    mensaje = respuesta.get_json()["mensaje"]
    assert mensaje["propio"] is True and mensaje["autor"] == "Yo"
    assert mensaje["cuerpo"] == "Hola <b>Tomás</b>\n¿vamos?"
    assert mensaje["id"] > 0 and mensaje["hora"]


def test_enviar_vacio_por_fetch_es_error_y_sin_js_sigue_redirigiendo(client):
    ingresar(client)
    error = client.post("/estudiantes/3/chat", data={"cuerpo": "   "}, headers=FETCH)
    assert error.status_code == 400 and "entre 1 y 2000" in error.get_json()["error"]
    assert client.post("/estudiantes/3/chat", data={"cuerpo": "Sin JS"}).status_code == 302


def test_nuevos_trae_solo_lo_posterior_y_marca_leido(app, client):
    mica = ingresar(client)
    tomas = ingresar(app.test_client(), "tomas@davinci.edu.ar")
    primero = mica.post("/estudiantes/3/chat", data={"cuerpo": "Uno"}, headers=FETCH).get_json()["mensaje"]["id"]
    tomas.post("/estudiantes/2/chat", data={"cuerpo": "Dos"}, headers=FETCH)
    tomas.post("/estudiantes/2/chat", data={"cuerpo": "Tres"}, headers=FETCH)

    datos = mica.get(f"/estudiantes/3/chat/nuevos?desde={primero}").get_json()
    assert [m["cuerpo"] for m in datos["mensajes"]] == ["Dos", "Tres"]
    assert all(not m["propio"] and m["autor"] == "Tomás" for m in datos["mensajes"])
    ultimo = datos["mensajes"][-1]["id"]
    assert mica.get(f"/estudiantes/3/chat/nuevos?desde={ultimo}").get_json()["mensajes"] == []
    with app.app_context():
        assert db.query_one("SELECT count(*) AS n FROM mensajes WHERE receptor_id = 2 AND leido = 0")["n"] == 0
        assert db.query_one("SELECT count(*) AS n FROM notificaciones WHERE usuario_id = 2 AND leida = 0")["n"] == 0


def test_un_tercero_no_lee_mensajes_ajenos_por_la_ruta_json(app, client):
    mica = ingresar(client)
    mica.post("/estudiantes/3/chat", data={"cuerpo": "Privado"}, headers=FETCH)
    lucia = ingresar(app.test_client(), "lucia@davinci.edu.ar")
    assert lucia.get("/estudiantes/3/chat/nuevos?desde=0").get_json()["mensajes"] == []
    assert lucia.get("/estudiantes/4/chat/nuevos?desde=0").status_code == 404
    admin = ingresar(app.test_client(), "admin@davinci.edu.ar")
    assert admin.get("/estudiantes/3/chat/nuevos?desde=0").status_code == 403
    assert app.test_client().get("/estudiantes/3/chat/nuevos").status_code == 302


def test_estado_de_la_bandeja_y_la_campana(app, client):
    mica = ingresar(client)
    tomas = ingresar(app.test_client(), "tomas@davinci.edu.ar")
    tomas.post("/estudiantes/2/chat", data={"cuerpo": "¿Llegaste?"}, headers=FETCH)
    estado = mica.get("/estudiantes/chats/estado").get_json()
    assert estado["avisos"] == 1 and estado["mensajes"] == 1
    assert "¿Llegaste?" in estado["bandeja"] and "chat-bandeja-nueva" in estado["bandeja"]
    assert mica.get("/notificaciones/contador").get_json() == {"avisos": 1}


def test_pagina_del_chat_trae_lo_necesario_para_actualizarse(client):
    ingresar(client)
    client.post("/estudiantes/3/chat", data={"cuerpo": "Hola"}, headers=FETCH)
    html = client.get("/estudiantes/3/chat").get_data(as_text=True)
    assert 'data-nuevos="/estudiantes/3/chat/nuevos"' in html
    assert "data-mensaje-id=" in html and "chat_vivo.js" in html


def _cargar(app, cantidad, emisor=3, receptor=2, leido=1):
    with app.app_context():
        for i in range(cantidad):
            db.execute(
                "INSERT INTO mensajes (emisor_id, receptor_id, cuerpo, leido, creado)"
                " VALUES (:e, :r, :c, :l, :t)",
                e=emisor if i % 2 == 0 else receptor, r=receptor if i % 2 == 0 else emisor,
                c=f"Historial {i:03d}", l=leido, t=f"2026-10-01T10:{i // 60:02d}:{i % 60:02d}+00:00",
            )


def test_el_chat_carga_solo_lo_ultimo_y_el_resto_bajo_demanda(app, client):
    _cargar(app, 75)
    ingresar(client)
    html = client.get("/estudiantes/3/chat").get_data(as_text=True)
    assert html.count("data-mensaje-id=") == 30
    assert "Historial 074" in html and "Historial 044" not in html
    assert 'data-anteriores="/estudiantes/3/chat/anteriores"' in html
    primero = int(html.split('data-mensaje-id="', 1)[1].split('"', 1)[0])
    pagina = client.get(f"/estudiantes/3/chat/anteriores?antes={primero}").get_json()
    assert pagina["mensajes"][0]["cuerpo"] == "Historial 015"
    assert len(pagina["mensajes"]) == 30 and pagina["hay_mas"] is True
    ultima = client.get(f"/estudiantes/3/chat/anteriores?antes={pagina['mensajes'][0]['id']}").get_json()
    assert len(ultima["mensajes"]) == 15 and ultima["hay_mas"] is False
    assert ultima["mensajes"][0]["cuerpo"] == "Historial 000"


def test_al_entrar_con_varios_nuevos_se_cargan_todos_y_se_marca_el_primero(app, client):
    _cargar(app, 20)
    with app.app_context():
        for i in range(40):
            db.execute(
                "INSERT INTO mensajes (emisor_id, receptor_id, cuerpo, leido, creado)"
                " VALUES (3, 2, :c, 0, :t)",
                c=f"Nuevo {i:02d}", t=f"2026-10-02T10:00:{i:02d}+00:00",
            )
    ingresar(client)
    html = client.get("/estudiantes/3/chat").get_data(as_text=True)
    assert "Nuevo 00" in html and "Nuevo 39" in html
    separador = html.index("chat-separador-nuevos")
    assert html.index("Historial 019") < separador < html.index("Nuevo 00")
    assert "40 mensajes nuevos" in html
    assert "chat-separador-nuevos" not in client.get("/estudiantes/3/chat").get_data(as_text=True)


def test_anteriores_respeta_la_privacidad(app, client):
    _cargar(app, 5)
    lucia = ingresar(app.test_client(), "lucia@davinci.edu.ar")
    assert lucia.get("/estudiantes/3/chat/anteriores?antes=999999").get_json()["mensajes"] == []
