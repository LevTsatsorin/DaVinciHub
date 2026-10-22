from io import BytesIO

import pytest
from werkzeug.security import check_password_hash

from davincihub import db


@pytest.fixture(autouse=True)
def sin_mensajes_demo(app):
    with app.app_context():
        db.execute("DELETE FROM mensajes")


def ingresar(client, email="mica@davinci.edu.ar"):
    return client.post("/auth/login", data={"email": email, "password": "davinci123"})


def test_perfil_publico_no_expone_email(client):
    respuesta = client.get("/estudiantes/2")
    contenido = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert "Mica Suárez" in contenido
    assert "mica@davinci.edu.ar" not in contenido
    assert "Reputación" in contenido


def test_dueno_puede_subir_foto_y_se_muestra_en_perfil(client, app):
    ingresar(client)
    imagen_png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
    )
    respuesta = client.post(
        "/estudiantes/2/editar",
        data={
            "nombre": "Mica",
            "apellido": "Suárez",
            "email": "mica@davinci.edu.ar",
            "carrera_id": "1",
            "anio": "2",
            "comision": "A",
            "foto": (BytesIO(imagen_png), "avatar.png"),
        },
    )
    assert respuesta.status_code == 302
    perfil = client.get("/estudiantes/2").get_data(as_text=True)
    assert 'class="ficha-usuario-avatar perfil-avatar" src="/estudiantes/2/foto"' in perfil
    descarga = client.get("/estudiantes/2/foto")
    assert descarga.status_code == 200
    assert descarga.mimetype == "image/png"
    assert descarga.data == imagen_png
    with app.app_context():
        assert db.query_one("SELECT tipo FROM fotos_perfil WHERE usuario_id = :id", id=2)["tipo"] == "image/png"


def test_no_acepta_archivos_que_no_sean_imagenes(client, app):
    ingresar(client)
    respuesta = client.post(
        "/estudiantes/2/editar",
        data={
            "nombre": "Mica",
            "apellido": "Suárez",
            "email": "mica@davinci.edu.ar",
            "carrera_id": "1",
            "anio": "2",
            "comision": "A",
            "foto": (BytesIO(b"<svg onload=alert(1) />"), "avatar.svg"),
        },
    )
    assert respuesta.status_code == 200
    assert "Usá una imagen PNG, JPG, GIF o WebP válida" in respuesta.get_data(as_text=True)
    with app.app_context():
        assert db.query_one("SELECT usuario_id FROM fotos_perfil WHERE usuario_id = :id", id=2) is None


def test_perfil_muestra_catedras_y_actividad(client):
    respuesta = client.get("/estudiantes/4")
    contenido = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert "Lógica de la Programación" in contenido
    assert "lucia@davinci.edu.ar" not in contenido


def test_perfil_cuenta_todas_las_actividades(client, app):
    with app.app_context():
        antes = db.query_one(
            "SELECT count(*) AS n FROM inscripciones i JOIN actividades a ON a.id = i.actividad_id"
            " WHERE i.usuario_id = 2 AND a.estado = 'aprobada'"
        )["n"]
        for indice in range(6):
            actividad = db.query_one(
                "INSERT INTO actividades"
                " (creador_id, nombre, descripcion, inicio, ubicacion, cupo_maximo, estado, creado)"
                " VALUES (1, :nombre, 'Descripción', '2026-11-01', 'Aula', 20, 'aprobada',"
                " '2026-10-19') RETURNING id",
                nombre=f"Actividad {indice}",
            )
            db.execute(
                "INSERT INTO inscripciones (actividad_id, usuario_id, creado)"
                " VALUES (:actividad, 2, '2026-10-19')",
                actividad=actividad["id"],
            )
    contenido = client.get("/estudiantes/2").get_data(as_text=True)
    assert f"Actividades</dt><dd>{antes + 6}</dd>" in contenido


def test_solo_dueno_edita_perfil(client, app):
    ingresar(client)
    editor = client.get("/estudiantes/2/editar").get_data(as_text=True)
    assert "materias_catedra" not in editor
    avatar_fin = editor.index("</label>", editor.index('class="perfil-selector-foto"'))
    boton_mas = editor.index('class="perfil-foto-mas"')
    assert boton_mas > avatar_fin
    respuesta = client.post(
        "/estudiantes/2/editar",
        data={
            "nombre": "Micaela",
            "apellido": "Suárez",
            "email": "mica@davinci.edu.ar",
            "carrera_id": "1",
            "anio": "3",
            "comision": "C",
        },
    )
    assert respuesta.status_code == 302
    with app.app_context():
        mica = db.query_one("SELECT * FROM usuarios WHERE id = :id", id=2)
    assert (mica["nombre"], mica["anio"], mica["comision"]) == ("Micaela", 3, "C")
    assert client.get("/estudiantes/2/editar").status_code == 200
    assert client.get("/estudiantes/3/editar").status_code == 403


def _editar_lucia(client, carrera_id):
    return client.post(
        "/estudiantes/4/editar",
        data={"nombre": "Lucía", "apellido": "Paz", "carrera_id": carrera_id, "anio": "3", "comision": "A"},
    )


def test_el_estudiante_no_elige_sus_materias_de_catedra(client, app):
    ingresar(client, "lucia@davinci.edu.ar")
    with app.app_context():
        carrera = db.query_one("SELECT carrera_id FROM usuarios WHERE id = 4")["carrera_id"]
    assert _editar_lucia(client, str(carrera)).status_code == 302
    with app.app_context():
        assert db.query_one("SELECT catedra FROM usuarios WHERE id = 4")["catedra"] == 1


def test_cambiar_de_carrera_quita_el_rol_de_catedra(client, app):
    ingresar(client, "lucia@davinci.edu.ar")
    with app.app_context():
        otra = db.query_one(
            "SELECT id FROM carreras WHERE activa = 1 AND id <> (SELECT carrera_id FROM usuarios WHERE id = 4)"
        )["id"]
    assert _editar_lucia(client, str(otra)).status_code == 302
    with app.app_context():
        assert db.query_one("SELECT catedra FROM usuarios WHERE id = 4")["catedra"] == 0
    assert "Materias de cátedra" not in client.get("/estudiantes/4").get_data(as_text=True)


def test_sin_valoraciones_se_aclara_y_se_puede_escribir(client):
    ingresar(client)
    contenido = client.get("/estudiantes/3").get_data(as_text=True)
    assert "Sin valoraciones todavía" in contenido
    assert 'href="/estudiantes/3/chat"' in contenido


def test_la_solicitud_y_la_aceptacion_avisan(client, app):
    ingresar(client)
    client.post("/estudiantes/3/conexiones")
    tomas = app.test_client()
    ingresar(tomas, email="tomas@davinci.edu.ar")
    tomas.post("/estudiantes/3/conexiones/2/aceptar")
    with app.app_context():
        aviso_tomas = db.query_one("SELECT * FROM notificaciones WHERE usuario_id = 3 AND tipo = 'conexion'")
        aviso_mica = db.query_one("SELECT * FROM notificaciones WHERE usuario_id = 2 AND tipo = 'conexion'")
    assert aviso_tomas["enlace"] == "/estudiantes/3/conexiones" and "Mica" in aviso_tomas["cuerpo"]
    assert aviso_mica["enlace"] == "/estudiantes/3" and "aceptó" in aviso_mica["cuerpo"]


def test_solicitud_conexion_y_chat(client, app):
    ingresar(client)
    respuesta = client.post("/estudiantes/3/conexiones")
    assert respuesta.status_code == 302
    respuesta = client.post("/estudiantes/3/chat", data={"cuerpo": "¡Hola, Tomás!"})
    assert respuesta.status_code == 302
    conversacion = client.get("/estudiantes/3/chat").get_data(as_text=True)
    assert "¡Hola, Tomás!" in conversacion
    assert '<span class="chat-mensaje-autor">Yo</span>' in conversacion
    assert 'class="chat-mensaje chat-mensaje-propio"' in conversacion

    tomas = app.test_client()
    ingresar(tomas, email="tomas@davinci.edu.ar")
    tomas.post("/estudiantes/2/chat", data={"cuerpo": "Hola, Mica"})
    conversacion = client.get("/estudiantes/3/chat").get_data(as_text=True)
    assert '<span class="chat-mensaje-autor">Tomás</span>' in conversacion
    assert 'class="chat-mensaje chat-mensaje-ajeno"' in conversacion
    with app.app_context():
        conexion = db.query_one(
            "SELECT estado FROM conexiones WHERE solicitante_id = :yo AND receptor_id = :otro",
            yo=2,
            otro=3,
        )
        mensaje = db.query_one("SELECT * FROM mensajes WHERE emisor_id = :id", id=2)
    assert conexion["estado"] == "pendiente"
    assert mensaje["receptor_id"] == 3


def test_destinatario_acepta_o_rechaza_solicitudes(client, app):
    ingresar(client)
    client.post("/estudiantes/3/conexiones")
    assert client.post("/estudiantes/3/conexiones/2/aceptar").status_code == 403
    perfil_publico = client.get("/estudiantes/3").get_data(as_text=True)
    assert "Solicitudes recibidas" not in perfil_publico
    assert "Abrir chat" not in perfil_publico
    assert client.get("/estudiantes/3/conexiones").status_code == 403

    tomas = app.test_client()
    ingresar(tomas, email="tomas@davinci.edu.ar")
    contenido = tomas.get("/estudiantes/3/conexiones").get_data(as_text=True)
    assert "Solicitudes recibidas" in contenido
    assert "Mica Suárez" in contenido
    assert tomas.post("/estudiantes/3/conexiones/2/aceptar").status_code == 302
    conexiones = tomas.get("/estudiantes/3/conexiones").get_data(as_text=True)
    assert "Conexiones" in conexiones
    assert "Mica Suárez" in conexiones
    assert "Abrir chat" in conexiones

    client.post("/estudiantes/4/conexiones")
    lucia = app.test_client()
    ingresar(lucia, email="lucia@davinci.edu.ar")
    assert lucia.post("/estudiantes/4/conexiones/2/rechazar").status_code == 302
    with app.app_context():
        rechazado = db.query_one(
            "SELECT estado FROM conexiones WHERE solicitante_id = :yo AND receptor_id = :otro",
            yo=2,
            otro=4,
        )
    assert rechazado["estado"] == "rechazada"


def test_menu_de_usuario_muestra_avatar_y_opciones(client):
    ingresar(client)
    contenido = client.get("/").get_data(as_text=True)
    assert 'class="menu-perfil-avatar"' in contenido
    assert "Abrir menú de la cuenta" in contenido
    assert "Mi perfil" in contenido
    assert "Conexiones" in contenido


def test_cambio_contrasena_exige_la_actual(client, app):
    ingresar(client)
    respuesta = client.post(
        "/estudiantes/2/contrasena",
        data={"password_actual": "incorrecta", "password_nueva": "nueva-clave-123", "confirmar": "nueva-clave-123"},
    )
    assert respuesta.status_code == 302
    with app.app_context():
        hash_original = db.query_one("SELECT password_hash FROM usuarios WHERE id = :id", id=2)["password_hash"]
    assert check_password_hash(hash_original, "davinci123")
    respuesta = client.post(
        "/estudiantes/2/contrasena",
        data={"password_actual": "davinci123", "password_nueva": "nueva-clave-123", "confirmar": "nueva-clave-123"},
    )
    assert respuesta.status_code == 302
    with app.app_context():
        hash_nuevo = db.query_one("SELECT password_hash FROM usuarios WHERE id = :id", id=2)["password_hash"]
    assert check_password_hash(hash_nuevo, "nueva-clave-123")


def _avisos_de_chat(app, usuario_id, enlace):
    with app.app_context():
        return db.query(
            "SELECT * FROM notificaciones WHERE usuario_id = :u AND enlace = :e", u=usuario_id, e=enlace
        )


def test_un_mensaje_nuevo_avisa_una_sola_vez_hasta_que_se_lee(client, app):
    ingresar(client)
    client.post("/estudiantes/3/chat", data={"cuerpo": "Hola"})
    client.post("/estudiantes/3/chat", data={"cuerpo": "¿Estás?"})
    avisos = _avisos_de_chat(app, 3, "/estudiantes/2/chat")
    assert len(avisos) == 1 and "Mica" in avisos[0]["cuerpo"] and avisos[0]["leida"] == 0

    tomas = app.test_client()
    ingresar(tomas, email="tomas@davinci.edu.ar")
    tomas.get("/estudiantes/2/chat")
    assert _avisos_de_chat(app, 3, "/estudiantes/2/chat")[0]["leida"] == 1

    client.post("/estudiantes/3/chat", data={"cuerpo": "Otra cosa"})
    assert len(_avisos_de_chat(app, 3, "/estudiantes/2/chat")) == 2
    assert _avisos_de_chat(app, 2, "/estudiantes/3/chat") == []


def test_bandeja_de_chat_muestra_vacio_y_chat_png(client):
    ingresar(client)
    contenido = client.get("/estudiantes/chats").get_data(as_text=True)
    assert "Todavía no tenés conversaciones" in contenido
    assert 'src="/static/img/chat.png"' in contenido


def test_bandeja_ordena_conversaciones_y_marca_no_leidos(client, app):
    ingresar(client)
    with app.app_context():
        db.execute(
            "INSERT INTO mensajes (emisor_id, receptor_id, cuerpo, creado)"
            " VALUES (2, 3, 'Mensaje anterior', '2026-10-19T10:00:00+00:00')"
        )
        db.execute(
            "INSERT INTO mensajes (emisor_id, receptor_id, cuerpo, creado)"
            " VALUES (4, 2, 'Mensaje más nuevo', '2026-10-20T10:00:00+00:00')"
        )
    contenido = client.get("/estudiantes/chats").get_data(as_text=True)
    assert contenido.index('href="/estudiantes/4/chat"') < contenido.index('href="/estudiantes/3/chat"')
    assert "Mensaje más nuevo" in contenido
    assert 'aria-label="1 mensaje sin leer"' in contenido

    client.get("/estudiantes/4/chat")
    with app.app_context():
        mensaje = db.query_one("SELECT leido FROM mensajes WHERE emisor_id = 4 AND receptor_id = 2")
    assert mensaje["leido"] == 1


def test_bandeja_resume_conversaciones_y_destaca_no_leidas(client, app):
    ingresar(client)
    with app.app_context():
        db.execute(
            "INSERT INTO mensajes (emisor_id, receptor_id, cuerpo, creado)"
            " VALUES (4, 2, 'Hola', '2026-10-20T10:00:00+00:00')"
        )
        db.execute(
            "INSERT INTO mensajes (emisor_id, receptor_id, cuerpo, creado)"
            " VALUES (2, 3, 'Chau', '2026-10-19T10:00:00+00:00')"
        )
    contenido = client.get("/estudiantes/chats").get_data(as_text=True)
    assert "fondo-oscuro" in contenido
    assert "<strong>2</strong> conversaciones" in contenido
    assert "<strong>1</strong> sin leer" in contenido
    assert contenido.count("chat-bandeja-nueva") == 1


def test_el_chat_vuelve_a_la_bandeja(client):
    ingresar(client)
    contenido = client.get("/estudiantes/3/chat").get_data(as_text=True)
    assert 'class="chat-volver" href="/estudiantes/chats"' in contenido
    assert 'href="/estudiantes/3"' in contenido
    assert 'src="/static/img/chat.png"' in contenido


def test_el_chat_cuenta_saltos_de_linea_como_el_navegador(client, app):
    ingresar(client)
    cuerpo = "linea\r\n" * 300
    assert client.post("/estudiantes/3/chat", data={"cuerpo": cuerpo}).status_code == 302
    with app.app_context():
        guardado = db.query_one("SELECT cuerpo FROM mensajes WHERE emisor_id = 2")["cuerpo"]
    assert "\r" not in guardado and len(guardado) == 1799


def test_un_tercer_estudiante_no_ve_mensajes_entre_otros_dos(client, app):
    ingresar(client)
    client.post("/estudiantes/3/chat", data={"cuerpo": "Mensaje privado"})
    lucia = app.test_client()
    ingresar(lucia, email="lucia@davinci.edu.ar")
    contenido = lucia.get("/estudiantes/3/chat").get_data(as_text=True)
    assert "Todavía no hay mensajes" in contenido
    assert "Mensaje privado" not in contenido


def test_chat_rechaza_mensaje_vacio_y_cuentas_bloqueadas(client, app):
    ingresar(client)
    vacio = client.post("/estudiantes/3/chat", data={"cuerpo": "   "})
    assert vacio.status_code == 200
    assert "El mensaje debe tener entre 1 y 2000 caracteres" in vacio.get_data(as_text=True)
    with app.app_context():
        db.execute("UPDATE usuarios SET bloqueado = 1 WHERE id = 3")
    assert client.get("/estudiantes/3/chat").status_code == 404
    assert client.post("/estudiantes/3/chat", data={"cuerpo": "No enviar"}).status_code == 404


def test_la_cabecera_muestra_el_nombre(client):
    ingresar(client)
    assert '<span class="usuario-nombre">Mica</span>' in client.get("/").get_data(as_text=True)


def test_un_admin_no_pide_conexion_ni_escribe_por_chat(client, app):
    ingresar(client, "admin@davinci.edu.ar")
    perfil = client.get("/estudiantes/2").get_data(as_text=True)
    assert "Pedir conexión" not in perfil and "Escribir mensaje" not in perfil
    assert 'href="/admin/usuarios/2"' in perfil
    assert client.post("/estudiantes/2/conexiones").status_code == 403
    assert client.get("/estudiantes/chats").status_code == 403
    assert client.get("/estudiantes/2/chat").status_code == 403
    assert client.post("/estudiantes/2/chat", data={"cuerpo": "Hola"}).status_code == 403
    with app.app_context():
        assert db.query_one("SELECT count(*) AS n FROM conexiones WHERE solicitante_id = 1")["n"] == 0
        assert db.query_one("SELECT count(*) AS n FROM mensajes WHERE emisor_id = 1")["n"] == 0


def test_un_estudiante_no_puede_iniciar_un_chat_con_si_mismo(client):
    ingresar(client)
    assert client.get("/estudiantes/2/chat").status_code == 404


def test_el_email_no_se_cambia_desde_el_perfil(client, app):
    ingresar(client)
    client.post(
        "/estudiantes/2/editar",
        data={"nombre": "Mica", "apellido": "Suárez", "email": "otra@davinci.edu.ar",
              "carrera_id": "1", "anio": "2", "comision": "A"},
    )
    with app.app_context():
        assert db.query_one("SELECT email FROM usuarios WHERE id = 2")["email"] == "mica@davinci.edu.ar"


def test_el_chat_usa_la_gamma_elegida(client, app):
    ingresar(client)
    assert 'class="chat-panel chat-tema-davinci"' in client.get("/estudiantes/3/chat").get_data(as_text=True)
    respuesta = client.post("/estudiantes/3/chat/tema", data={"tema": "noche"})
    assert respuesta.status_code == 302 and respuesta.location == "/estudiantes/3/chat"
    contenido = client.get("/estudiantes/4/chat").get_data(as_text=True)
    assert 'class="chat-panel chat-tema-noche"' in contenido
    assert 'value="noche" aria-pressed="true"' in contenido
    assert client.post("/estudiantes/3/chat/tema", data={"tema": "rojo"}).status_code == 400
    with app.app_context():
        assert db.query_one("SELECT chat_tema FROM usuarios WHERE id = 2")["chat_tema"] == "noche"


def test_un_admin_no_elige_gamma_de_chat(client):
    ingresar(client, email="admin@davinci.edu.ar")
    assert client.post("/estudiantes/3/chat/tema", data={"tema": "noche"}).status_code == 403
