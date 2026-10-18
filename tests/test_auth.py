from davincihub import db

PASO1 = {
    "nombre": "Nuevo",
    "apellido": "Estudiante",
    "email": "nuevo@davinci.edu.ar",
    "password": "clave-segura-1",
    "confirmar": "clave-segura-1",
}

DATOS_ESTUDIANTE = {"carrera_id": "1", "anio": "1", "comision": "A"}


def registrar(client, **cambios):
    return client.post("/auth/registro", data=PASO1 | cambios)


def login(client, email="mica@davinci.edu.ar", password="davinci123"):
    return client.post("/auth/login", data={"email": email, "password": password})


def test_registro_paso1_ok(client, app):
    respuesta = registrar(client)
    assert respuesta.status_code == 302
    assert "/auth/registro/datos" in respuesta.headers["Location"]
    with client.session_transaction() as sesion:
        assert "usuario_id" in sesion
    with app.app_context():
        usuario = db.query_one("SELECT * FROM usuarios WHERE email = :email", email=PASO1["email"])
    assert usuario is not None
    assert usuario["apellido"] == "Estudiante"
    assert usuario["carrera_id"] is None
    assert usuario["password_hash"] != PASO1["password"]


def test_registro_email_duplicado(client):
    registrar(client)
    client.post("/auth/salir")
    respuesta = registrar(client)
    assert respuesta.status_code == 200
    assert "ya está registrado" in respuesta.get_data(as_text=True)


def test_registro_password_no_coincide(client):
    respuesta = registrar(client, confirmar="otra-clave-123")
    assert respuesta.status_code == 200
    assert "no coinciden" in respuesta.get_data(as_text=True)


def test_registro_campos_vacios(client):
    respuesta = client.post("/auth/registro", data={})
    assert respuesta.status_code == 200
    assert "Campo obligatorio" in respuesta.get_data(as_text=True)


def test_registro_paso2_ok(client, app):
    registrar(client)
    respuesta = client.post("/auth/registro/datos", data=DATOS_ESTUDIANTE)
    assert respuesta.status_code == 302
    with app.app_context():
        usuario = db.query_one("SELECT * FROM usuarios WHERE email = :email", email=PASO1["email"])
    assert usuario["carrera_id"] == 1
    assert usuario["anio"] == 1
    assert usuario["comision"] == "A"


def test_registro_paso2_requiere_login(client):
    respuesta = client.post("/auth/registro/datos", data=DATOS_ESTUDIANTE)
    assert respuesta.status_code == 302
    assert "/auth/login" in respuesta.headers["Location"]


def test_registro_paso2_carrera_inexistente(client):
    registrar(client)
    respuesta = client.post("/auth/registro/datos", data=DATOS_ESTUDIANTE | {"carrera_id": "999"})
    assert respuesta.status_code == 200
    assert "Elegí una carrera válida" in respuesta.get_data(as_text=True)


def test_registro_paso2_anio_fuera_de_rango(client):
    registrar(client)
    respuesta = client.post(
        "/auth/registro/datos", data=DATOS_ESTUDIANTE | {"anio": "99999999999999999999"}
    )
    assert respuesta.status_code == 200
    assert "entre 1 y 10" in respuesta.get_data(as_text=True)


def test_login_ok(client):
    respuesta = login(client)
    assert respuesta.status_code == 302
    with client.session_transaction() as sesion:
        assert "usuario_id" in sesion


def test_login_password_malo(client):
    respuesta = login(client, password="incorrecta")
    assert respuesta.status_code == 200
    assert "Email o contraseña incorrectos" in respuesta.get_data(as_text=True)


def test_login_email_inexistente(client):
    respuesta = login(client, email="nadie@davinci.edu.ar")
    assert respuesta.status_code == 200
    assert "Email o contraseña incorrectos" in respuesta.get_data(as_text=True)


def test_salir(client):
    login(client)
    respuesta = client.post("/auth/salir")
    assert respuesta.status_code == 302
    with client.session_transaction() as sesion:
        assert "usuario_id" not in sesion


def test_protegida_requiere_login(client_rutas):
    respuesta = client_rutas.get("/protegida")
    assert respuesta.status_code == 302
    assert "/auth/login" in respuesta.headers["Location"]


def test_admin_url_prohibida_a_estudiante(client_rutas):
    login(client_rutas)
    assert client_rutas.get("/solo-admin").status_code == 403


def test_admin_url_permitida_a_admin(client_rutas):
    login(client_rutas, email="admin@davinci.edu.ar")
    assert client_rutas.get("/solo-admin").status_code == 200


def test_usuario_bloqueado_expulsado(client_rutas, app):
    login(client_rutas)
    with app.app_context():
        db.execute("UPDATE usuarios SET bloqueado = 1 WHERE email = :email",
                   email="mica@davinci.edu.ar")
    respuesta = client_rutas.get("/protegida")
    assert respuesta.status_code == 403
    with client_rutas.session_transaction() as sesion:
        assert "usuario_id" not in sesion


def test_login_usuario_bloqueado(client, app):
    with app.app_context():
        db.execute("UPDATE usuarios SET bloqueado = 1 WHERE email = :email",
                   email="mica@davinci.edu.ar")
    respuesta = login(client)
    assert respuesta.status_code == 200
    assert "bloqueada" in respuesta.get_data(as_text=True)


def test_registro_paso2_anio_superindice(client):
    registrar(client)
    respuesta = client.post("/auth/registro/datos", data=DATOS_ESTUDIANTE | {"anio": "²"})
    assert respuesta.status_code == 200
    assert "entre 1 y 10" in respuesta.get_data(as_text=True)


def test_registro_paso2_carrera_superindice(client):
    registrar(client)
    respuesta = client.post("/auth/registro/datos", data=DATOS_ESTUDIANTE | {"carrera_id": "²"})
    assert respuesta.status_code == 200
    assert "Elegí una carrera válida" in respuesta.get_data(as_text=True)
