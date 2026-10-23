import sqlite3

import pytest

from davincihub import db
from davincihub.app import create_app
from davincihub.objetos import datos

FORM = {
    "titulo": "Tableta gráfica Wacom",
    "descripcion": "Incluye lápiz y cable. Funciona correctamente.",
    "categoria": "dibujo_diseno",
    "estado_objeto": "usado_buen_estado",
    "modalidad": "venta",
    "precio": "25000.50",
    "carrera_id": "1",
}


@pytest.fixture(autouse=True)
def catalogo_vacio(app):
    # Cada escenario de C1 controla sus publicaciones, independientemente de los ejemplos demo.
    with app.app_context():
        db.execute("DELETE FROM publicaciones")


@pytest.fixture
def estudiante(client):
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = 2
    return client


@pytest.fixture
def publicacion(app):
    with app.app_context():
        return datos.crear(2, FORM)


@pytest.mark.parametrize("ruta", ["/objetos/", "/objetos/publicar", "/objetos/mis-publicaciones"])
def test_objetos_requiere_login(client, ruta):
    respuesta = client.get(ruta)
    assert respuesta.status_code == 302
    assert "/auth/login" in respuesta.location


def test_crear_y_ver_publicacion(estudiante, app):
    respuesta = estudiante.post("/objetos/publicar", data=FORM | {"autor_id": "3"})
    assert respuesta.status_code == 302
    detalle = estudiante.get(respuesta.location)
    assert detalle.status_code == 200
    assert "$25.000,50" in detalle.text
    assert "Usado en buen estado" in detalle.text
    with app.app_context():
        p = db.query_one("SELECT * FROM publicaciones")
        assert p["autor_id"] == 2
        assert p["carrera_id"] == 1
    assert FORM["titulo"] in estudiante.get("/objetos/?mostrar_mias=1").text


@pytest.mark.parametrize("precio", ["", "0", "-1", "NaN", "Infinity", "abc", "1.001", "1000000000"])
def test_venta_rechaza_precio_invalido(estudiante, app, precio):
    respuesta = estudiante.post("/objetos/publicar", data=FORM | {"precio": precio})
    assert respuesta.status_code == 400
    assert 'id="error-precio"' in respuesta.text
    assert FORM["titulo"] in respuesta.text  # conserva el formulario
    with app.app_context():
        assert db.query_one("SELECT count(*) AS n FROM publicaciones")["n"] == 0


@pytest.mark.parametrize("modalidad", ["intercambio", "prestamo"])
def test_no_guarda_precio_fuera_de_venta(estudiante, app, modalidad):
    assert estudiante.post("/objetos/publicar", data=FORM | {
        "modalidad": modalidad, "precio": "999", "carrera_id": "",
    }).status_code == 302
    with app.app_context():
        p = db.query_one("SELECT precio, carrera_id FROM publicaciones")
        assert p == {"precio": None, "carrera_id": None}


@pytest.mark.parametrize("cambios,campo", [
    ({"titulo": " "}, "titulo"),
    ({"titulo": "a" * 121}, "titulo"),
    ({"descripcion": ""}, "descripcion"),
    ({"descripcion": "a" * 2001}, "descripcion"),
    ({"categoria": "ropa"}, "categoria"),
    ({"estado_objeto": "roto"}, "estado_objeto"),
    ({"modalidad": "alquiler"}, "modalidad"),
    ({"carrera_id": "999999"}, "carrera_id"),
    ({"carrera_id": "²"}, "carrera_id"),
    ({"carrera_id": "9" * 100}, "carrera_id"),
])
def test_valida_campos_en_servidor(estudiante, cambios, campo):
    respuesta = estudiante.post("/objetos/publicar", data=FORM | cambios)
    assert respuesta.status_code == 400
    assert f'id="error-{campo}"' in respuesta.text


def test_filtros_combinados_y_busqueda_sin_acentos(estudiante, app, publicacion):
    with app.app_context():
        datos.crear(3, FORM | {"titulo": "Libro de cine", "categoria": "libros_apuntes",
                              "modalidad": "prestamo", "carrera_id": "2"})
    respuesta = estudiante.get("/objetos/", query_string={
        "mostrar_mias": "1", "q": "GRAFICA", "categoria": "dibujo_diseno", "modalidad": "venta", "carrera_id": "1",
    })
    assert FORM["titulo"] in respuesta.text
    assert "Libro de cine" not in respuesta.text
    assert FORM["titulo"] not in estudiante.get("/objetos/?carrera_id=2").text
    assert FORM["titulo"] not in estudiante.get("/objetos/?modalidad=prestamo").text
    assert FORM["titulo"] not in estudiante.get("/objetos/?categoria=audio_iluminacion").text


@pytest.mark.parametrize("texto", ["%", "_", "!", "' OR 1=1 --"])
def test_busqueda_no_interpreta_comodines_ni_sql(estudiante, publicacion, texto):
    assert FORM["titulo"] not in estudiante.get("/objetos/", query_string={"q": texto, "mostrar_mias": "1"}).text


def test_dueno_edita_y_quita_precio_al_cambiar_modalidad(estudiante, app, publicacion):
    respuesta = estudiante.post(f"/objetos/{publicacion}/editar", data=FORM | {
        "titulo": "Tableta actualizada", "modalidad": "prestamo",
    })
    assert respuesta.status_code == 302
    with app.app_context():
        p = datos.obtener(publicacion)
        assert p["titulo"] == "Tableta actualizada"
        assert p["precio"] is None


def test_edicion_invalida_conserva_datos(estudiante, app, publicacion):
    assert estudiante.post(f"/objetos/{publicacion}/editar", data=FORM | {
        "titulo": "No guardar", "precio": "-5",
    }).status_code == 400
    with app.app_context():
        assert datos.obtener(publicacion)["titulo"] == FORM["titulo"]


def test_otra_persona_no_edita_ni_cambia_estado(client, app, publicacion):
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = 3
    assert client.get(f"/objetos/{publicacion}/editar").status_code == 403
    assert client.post(f"/objetos/{publicacion}/editar", data=FORM).status_code == 403
    assert client.post(f"/objetos/{publicacion}/estado", data={"estado": "cerrada"}).status_code == 403
    with app.app_context():
        assert datos.obtener(publicacion)["estado"] == "activa"
        with pytest.raises(PermissionError):
            datos.editar(publicacion, 3, FORM)


def test_pausa_reactivacion_y_cierre(estudiante, app, publicacion):
    url = f"/objetos/{publicacion}"
    assert estudiante.post(url + "/estado", data={"estado": "pausada"}).status_code == 302
    assert FORM["titulo"] not in estudiante.get("/objetos/").text
    assert FORM["titulo"] in estudiante.get("/objetos/mis-publicaciones?estado=pausada").text
    assert estudiante.get(url).status_code == 200
    assert estudiante.post(url + "/estado", data={"estado": "activa"}).status_code == 302
    assert FORM["titulo"] in estudiante.get("/objetos/?mostrar_mias=1").text
    assert estudiante.post(url + "/estado", data={"estado": "cerrada"}).status_code == 302
    assert estudiante.post(url + "/estado", data={"estado": "activa"}).status_code == 409
    assert estudiante.post(url + "/editar", data=FORM).status_code == 409
    with app.app_context():
        assert datos.obtener(publicacion)["estado"] == "cerrada"


def test_no_se_puede_forzar_estado_del_catalogo(estudiante, app, publicacion):
    with app.app_context():
        datos.cambiar_estado(publicacion, 2, "pausada")
    assert FORM["titulo"] not in estudiante.get("/objetos/?estado=pausada").text


def test_publicacion_no_activa_solo_visible_al_dueno(client, app, publicacion):
    with app.app_context():
        datos.cambiar_estado(publicacion, 2, "pausada")
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = 3
    assert client.get(f"/objetos/{publicacion}").status_code == 404
    assert FORM["titulo"] not in client.get("/objetos/mis-publicaciones").text


def test_admin_consulta_pero_no_publica(client, app, publicacion):
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = 1
    assert client.get("/objetos/").status_code == 200
    assert client.get("/objetos/publicar").status_code == 403
    assert client.post("/objetos/publicar", data=FORM).status_code == 403
    assert client.post(f"/objetos/{publicacion}/estado", data={"estado": "pausada"}).status_code == 403
    with app.app_context(), pytest.raises(PermissionError):
        datos.crear(1, FORM)


def test_no_muestra_publicaciones_de_usuario_bloqueado(client, app, publicacion):
    with app.app_context():
        db.execute("UPDATE usuarios SET bloqueado = 1 WHERE id = 2")
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = 3
    assert FORM["titulo"] not in client.get("/objetos/").text
    assert client.get(f"/objetos/{publicacion}").status_code == 404


def test_bloqueado_no_publica(estudiante, app):
    with app.app_context():
        db.execute("UPDATE usuarios SET bloqueado = 1 WHERE id = 2")
    assert estudiante.post("/objetos/publicar", data=FORM).status_code == 403


def test_carrera_inactiva_se_conserva_pero_no_se_asigna_a_otra_publicacion(app, publicacion):
    with app.app_context():
        db.execute("UPDATE carreras SET activa = 0 WHERE id = 1")
        datos.editar(publicacion, 2, FORM)
        assert datos.obtener(publicacion)["carrera_id"] == 1
        with pytest.raises(datos.ErrorPublicacion):
            datos.crear(3, FORM)


def test_paginacion_y_filtros_malformados(estudiante, app):
    with app.app_context():
        for n in range(14):
            datos.crear(2, FORM | {"titulo": f"Material {n}"})
        pagina = datos.listar({}, pagina=2)
        assert len(pagina["publicaciones"]) == 2
        assert pagina["total"] == 14
        assert datos.listar({}, pagina=999)["pagina"] == 2
    respuesta = estudiante.get("/objetos/?pagina=2&categoria=dibujo_diseno&mostrar_mias=1")
    assert respuesta.status_code == 200
    assert "Página 2 de 2" in respuesta.text
    assert "categoria=dibujo_diseno" in respuesta.text
    assert estudiante.get("/objetos/?pagina=abc&carrera_id=²&modalidad=invalid").status_code == 200


def test_escapa_contenido_del_usuario(estudiante):
    respuesta = estudiante.post("/objetos/publicar", data=FORM | {
        "titulo": "<script>alert(1)</script>", "descripcion": "<img src=x onerror=alert(1)>",
    })
    detalle = estudiante.get(respuesta.location)
    assert "<script>alert(1)</script>" not in detalle.text
    assert "&lt;script&gt;" in detalle.text
    assert "<img src=x" not in detalle.text


def test_csrf_en_publicacion_y_cambio_de_estado(estudiante, app, publicacion):
    app.config["WTF_CSRF_ENABLED"] = True
    assert estudiante.post("/objetos/publicar", data=FORM).status_code == 400
    assert estudiante.post(f"/objetos/{publicacion}/estado", data={"estado": "cerrada"}).status_code == 400


def test_migracion_conserva_publicaciones_existentes(tmp_path):
    ruta = tmp_path / "anterior.db"
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("CREATE TABLE publicaciones (id INTEGER PRIMARY KEY, titulo TEXT)")
        conexion.execute("INSERT INTO publicaciones VALUES (1, 'Libro existente')")
    config = {"DATABASE_URL": f"sqlite:///{ruta}"}
    create_app(config)
    create_app(config)  # idempotente
    with sqlite3.connect(ruta) as conexion:
        assert conexion.execute("SELECT titulo, carrera_id FROM publicaciones").fetchone() == (
            "Libro existente", None,
        )


def test_detalle_permite_escribirle_al_autor(client, publicacion):
    for usuario_id, ve_chat in ((3, True), (2, False), (1, False)):
        with client.session_transaction() as sesion:
            sesion["usuario_id"] = usuario_id
        contenido = client.get(f"/objetos/{publicacion}").get_data(as_text=True)
        assert ('href="/estudiantes/2/chat"' in contenido) is ve_chat


def test_catalogo_oculta_propias_y_permite_incluirlas(estudiante, app, publicacion):
    with app.app_context():
        datos.crear(3, FORM | {"titulo": "Cámara de otro estudiante"})
    ocultas = estudiante.get("/objetos/")
    assert FORM["titulo"] not in ocultas.text
    assert "Cámara de otro estudiante" in ocultas.text
    visibles = estudiante.get("/objetos/?mostrar_mias=1")
    assert FORM["titulo"] in visibles.text
    assert 'value="1" checked' in visibles.text
    assert FORM["titulo"] in estudiante.get("/objetos/mis-publicaciones").text


def test_paginacion_conserva_opcion_mostrar_propias(estudiante, app):
    with app.app_context():
        for n in range(14):
            datos.crear(2, FORM | {"titulo": f"Objeto propio {n}"})
    respuesta = estudiante.get("/objetos/?mostrar_mias=1")
    assert "mostrar_mias=1" in respuesta.text
    assert "Página 1 de 2" in respuesta.text
