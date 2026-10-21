import pytest

from davincihub import db
from davincihub.academico import datos

MULTIMEDIAL, VIDEOJUEGOS, WEB = 1, 2, 3


def login(client, email="admin@davinci.edu.ar"):
    return client.post("/auth/login", data={"email": email, "password": "davinci123"})


def _materia(nombre, carrera_id=MULTIMEDIAL):
    return db.query_one("SELECT * FROM materias WHERE nombre = :n AND carrera_id = :c", n=nombre, c=carrera_id)


@pytest.mark.parametrize(("metodo", "url"), [
    ("get", "/admin/carreras/"),
    ("get", f"/admin/carreras/{MULTIMEDIAL}"),
    ("get", "/admin/carreras/nueva"),
    ("post", f"/admin/carreras/{MULTIMEDIAL}/estado"),
    ("post", f"/admin/carreras/{MULTIMEDIAL}/materias"),
])
def test_un_estudiante_recibe_403(client, metodo, url):
    login(client, "mica@davinci.edu.ar")
    assert getattr(client, metodo)(url).status_code == 403


def test_el_listado_muestra_titulo_duracion_y_materias(client):
    login(client)
    texto = client.get("/admin/carreras/").get_data(as_text=True)
    assert "Diseño Multimedial" in texto and "Diseñador Multimedial" in texto
    assert "3 años" in texto and "35 materias" in texto


def test_el_plan_agrupa_las_materias_por_cuatrimestre(app):
    with app.app_context():
        plan = datos.plan_de_carrera(MULTIMEDIAL)
    assert [a["anio"] for a in plan] == [1, 2, 3]
    assert [c["numero"] for c in plan[0]["cuatrimestres"]] == [1, 2]
    assert "Lógica de la Programación" in [m["nombre"] for m in plan[0]["cuatrimestres"][0]["materias"]]


def test_crear_y_editar_una_carrera(client, app):
    login(client)
    client.post("/admin/carreras/nueva", data={"nombre": "Ilustración", "titulo": "Ilustrador", "duracion_anios": "2"})
    with app.app_context():
        carrera = db.query_one("SELECT * FROM carreras WHERE nombre = 'Ilustración'")
    assert carrera["titulo"] == "Ilustrador" and carrera["duracion_anios"] == 2 and carrera["activa"] == 1
    client.post(f"/admin/carreras/{carrera['id']}/editar",
                data={"nombre": "Ilustración Digital", "titulo": "", "duracion_anios": "3"})
    with app.app_context():
        carrera = datos.obtener_carrera(carrera["id"])
    assert carrera["nombre"] == "Ilustración Digital" and carrera["titulo"] is None and carrera["duracion_anios"] == 3


@pytest.mark.parametrize(("formulario", "mensaje"), [
    ({"nombre": "", "duracion_anios": "3"}, "nombre"),
    ({"nombre": "Nueva", "duracion_anios": "7"}, "entre 1 y 6"),
    ({"nombre": "Nueva", "duracion_anios": "tres"}, "entre 1 y 6"),
    ({"nombre": "diseño multimedial", "duracion_anios": "3"}, "Ya existe"),
])
def test_reglas_de_la_carrera(app, formulario, mensaje):
    with app.app_context(), pytest.raises(datos.ErrorAcademico, match=mensaje):
        datos.guardar_carrera(formulario)


def test_no_se_acorta_la_carrera_por_debajo_de_sus_materias(app):
    with app.app_context():
        with pytest.raises(datos.ErrorAcademico, match="cuatrimestre 6"):
            datos.guardar_carrera({"nombre": "Diseño Multimedial", "duracion_anios": "2"}, MULTIMEDIAL)
        assert datos.obtener_carrera(MULTIMEDIAL)["duracion_anios"] == 3


def test_agregar_y_editar_una_materia(client, app):
    login(client)
    client.post(f"/admin/carreras/{MULTIMEDIAL}/materias", data={"nombre": "Tipografía", "cuatrimestre": "3"})
    with app.app_context():
        materia = _materia("Tipografía")
    assert materia["cuatrimestre"] == 3 and materia["activa"] == 1
    client.post(f"/admin/carreras/materias/{materia['id']}/editar", data={"nombre": "Tipografía I", "cuatrimestre": "2"})
    with app.app_context():
        materia = datos.obtener_materia(materia["id"])
    assert materia["nombre"] == "Tipografía I" and materia["cuatrimestre"] == 2


def test_no_hay_dos_materias_con_el_mismo_nombre_en_una_carrera(app):
    with app.app_context():
        with pytest.raises(datos.ErrorAcademico, match="Ya existe"):
            datos.guardar_materia(MULTIMEDIAL, {"nombre": "logica de la programacion", "cuatrimestre": "1"})
        guion = _materia("Guión y Narrativa")
        with pytest.raises(datos.ErrorAcademico, match="Ya existe"):
            datos.guardar_materia(MULTIMEDIAL, {"nombre": "Lógica de la Programación", "cuatrimestre": "2"}, guion["id"])
        datos.guardar_materia(WEB, {"nombre": "Guión y Narrativa", "cuatrimestre": "1"})


@pytest.mark.parametrize("cuatrimestre", ["0", "5", "x", ""])
def test_el_cuatrimestre_esta_dentro_de_la_duracion_de_la_carrera(app, cuatrimestre):
    with app.app_context(), pytest.raises(datos.ErrorAcademico, match="cuatrimestre"):
        datos.guardar_materia(WEB, {"nombre": "Accesibilidad", "cuatrimestre": cuatrimestre})


def test_deshabilitar_una_carrera_la_saca_del_registro_sin_romper_perfiles(client, app):
    login(client)
    client.post(f"/admin/carreras/{MULTIMEDIAL}/estado", data={"activa": "0"})
    with app.app_context():
        assert not datos.obtener_carrera(MULTIMEDIAL)["activa"]
        assert MULTIMEDIAL not in {c["id"] for c in datos.carreras_activas()}
    client.post("/auth/salir")
    client.post("/auth/registro", data={"nombre": "Nuevo", "apellido": "Estudiante", "email": "nuevo@davinci.edu.ar",
                                        "password": "clave-segura-1", "confirmar": "clave-segura-1"})
    registro = client.get("/auth/registro/datos").get_data(as_text=True)
    assert "Diseño Multimedial" not in registro and "Diseño Gráfico" in registro
    respuesta = client.post("/auth/registro/datos", data={"carrera_id": str(MULTIMEDIAL), "anio": "1", "comision": "A"})
    assert "Elegí una carrera válida" in respuesta.get_data(as_text=True)
    client.post("/auth/salir")
    login(client, "mica@davinci.edu.ar")
    assert client.get("/reservas/mis-reservas/").status_code == 200
    client.post("/auth/salir")
    login(client)
    assert "Diseño Multimedial" in client.get("/admin/usuarios/2").get_data(as_text=True)


def test_deshabilitar_una_materia_no_la_borra(client, app):
    with app.app_context():
        logica = _materia("Lógica de la Programación")
    login(client)
    client.post(f"/admin/carreras/materias/{logica['id']}/estado", data={"activa": "0"})
    with app.app_context():
        assert datos.obtener_materia(logica["id"])["activa"] == 0
        assert logica["id"] not in {m["id"] for m in datos.materias_activas(MULTIMEDIAL)}
    texto = client.get(f"/admin/carreras/{MULTIMEDIAL}").get_data(as_text=True)
    assert "Lógica de la Programación" in texto and "Deshabilitada" in texto
    client.post(f"/admin/carreras/materias/{logica['id']}/estado", data={"activa": "1"})
    with app.app_context():
        assert datos.obtener_materia(logica["id"])["activa"] == 1


def test_carrera_inexistente_da_404(client):
    login(client)
    assert client.get("/admin/carreras/9999").status_code == 404
    assert client.get("/admin/carreras/materias/99999/editar").status_code == 404


def test_el_asistente_crea_la_carrera_con_su_plan(client, app):
    login(client)
    respuesta = client.post("/admin/carreras/nueva", data={
        "nombre": "Ilustración", "titulo": "Ilustrador", "duracion_anios": "2",
        "materias-1": ["Dibujo I", "Color", " "], "materias-3": ["Dibujo II"], "materias-2": [""],
    })
    assert respuesta.status_code == 302
    with app.app_context():
        carrera = db.query_one("SELECT id FROM carreras WHERE nombre = 'Ilustración'")
        materias = db.query("SELECT nombre, cuatrimestre FROM materias WHERE carrera_id = :c ORDER BY nombre",
                            c=carrera["id"])
    assert [(m["nombre"], m["cuatrimestre"]) for m in materias] == [("Color", 1), ("Dibujo I", 1), ("Dibujo II", 3)]


@pytest.mark.parametrize(("materias", "mensaje", "conservada"), [
    ({"materias-1": ["Dibujo", "dibujo"]}, "Ya existe", "dibujo"),
    ({"materias-5": ["Proyecto"]}, "cuatrimestre", "Proyecto"),
])
def test_si_falla_una_materia_no_se_crea_nada_y_vuelve_al_plan(client, app, materias, mensaje, conservada):
    login(client)
    respuesta = client.post("/admin/carreras/nueva", data={"nombre": "Ilustración", "duracion_anios": "2", **materias})
    texto = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200 and mensaje in texto
    assert 'data-paso-inicial="2"' in texto and f'value="{conservada}"' in texto
    with app.app_context():
        assert db.query_one("SELECT id FROM carreras WHERE nombre = 'Ilustración'") is None


def test_si_fallan_los_datos_generales_vuelve_al_primer_paso(client):
    login(client)
    texto = client.post("/admin/carreras/nueva", data={"nombre": "", "duracion_anios": "2",
                                                       "materias-1": ["Dibujo"]}).get_data(as_text=True)
    assert 'data-paso-inicial="1"' in texto and 'value="Dibujo"' in texto


def test_al_deshabilitar_la_carrera_se_ve_un_solo_aviso(client):
    login(client)
    texto = client.post(f"/admin/carreras/{MULTIMEDIAL}/estado", data={"activa": "0"},
                        follow_redirects=True).get_data(as_text=True)
    assert texto.count("deshabilitada") == 1 and "avisos-flotantes" not in texto
