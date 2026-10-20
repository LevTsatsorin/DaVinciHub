from io import BytesIO

from werkzeug.security import check_password_hash

from davincihub import db


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
    assert 'class="perfil-foto"' in perfil
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
    assert "Actividades</dt><dd>6</dd>" in contenido


def test_solo_dueno_edita_perfil(client, app):
    ingresar(client)
    editor = client.get("/estudiantes/2/editar").get_data(as_text=True)
    assert 'class="materias-cuadricula"' in editor
    assert editor.count('type="checkbox" name="materias_catedra"') > 10
    assert 'name="materias_catedra" multiple' not in editor
    assert "Administración de Proyectos" not in editor
    avatar_fin = editor.index("</label>", editor.index('class="perfil-selector-foto"'))
    boton_mas = editor.index('class="perfil-foto-mas"')
    assert boton_mas > avatar_fin
    assert 'name="materias_catedra" value="1"' in editor
    respuesta = client.post(
        "/estudiantes/2/editar",
        data={
            "nombre": "Micaela",
            "apellido": "Suárez",
            "email": "mica@davinci.edu.ar",
            "carrera_id": "1",
            "anio": "3",
            "comision": "C",
            "materias_catedra": ["3"],
        },
    )
    assert respuesta.status_code == 302
    with app.app_context():
        mica = db.query_one("SELECT * FROM usuarios WHERE id = :id", id=2)
        materias = db.query("SELECT materia_id FROM catedras WHERE usuario_id = :id", id=2)
    assert (mica["nombre"], mica["anio"], mica["comision"]) == ("Micaela", 3, "C")
    assert [fila["materia_id"] for fila in materias] == [3]
    assert client.get("/estudiantes/2/editar").status_code == 200
    assert client.get("/estudiantes/3/editar").status_code == 403


def test_materias_api_devuelve_solo_la_carrera_elegida(client, app):
    ingresar(client)
    respuesta = client.get("/estudiantes/2/materias?carrera_id=1")
    assert respuesta.status_code == 200
    ids = {materia["id"] for materia in respuesta.get_json()}
    with app.app_context():
        carrera = db.query(
            "SELECT id FROM materias WHERE carrera_id = :carrera AND activa = 1",
            carrera=1,
        )
    assert ids == {materia["id"] for materia in carrera}
    assert client.get("/estudiantes/2/materias?carrera_id=no-valida").status_code == 400
    assert client.get("/estudiantes/3/materias?carrera_id=1").status_code == 403


def test_edicion_rechaza_materia_de_otra_carrera(client, app):
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
            "materias_catedra": ["36"],
        },
    )
    assert respuesta.status_code == 200
    assert "Elegí materias válidas" in respuesta.get_data(as_text=True)
    with app.app_context():
        assert db.query_one("SELECT carrera_id FROM usuarios WHERE id = :id", id=2)["carrera_id"] == 1


def test_solicitud_conexion_y_chat(client, app):
    ingresar(client)
    respuesta = client.post("/estudiantes/3/conexiones")
    assert respuesta.status_code == 302
    respuesta = client.post("/estudiantes/3/chat", data={"cuerpo": "¡Hola, Tomás!"})
    assert respuesta.status_code == 302
    conversacion = client.get("/estudiantes/3/chat").get_data(as_text=True)
    assert "¡Hola, Tomás!" in conversacion
    assert '<span class="chat-mensaje-autor">Mica Suárez</span>' in conversacion
    assert 'class="chat-mensaje chat-mensaje-propio"' in conversacion

    tomas = app.test_client()
    ingresar(tomas, email="tomas@davinci.edu.ar")
    tomas.post("/estudiantes/2/chat", data={"cuerpo": "Hola, Mica"})
    conversacion = client.get("/estudiantes/3/chat").get_data(as_text=True)
    assert '<span class="chat-mensaje-autor">Tomás Vega</span>' in conversacion
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
    assert "Abrir menú de perfil" in contenido
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
