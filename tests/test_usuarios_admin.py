import pytest
from flask import render_template_string

from davincihub import db
from davincihub.usuarios import datos

ADMIN, MICA, TOMAS, LUCIA, BRUNO = 1, 2, 3, 4, 5


def login(client, email="admin@davinci.edu.ar"):
    return client.post("/auth/login", data={"email": email, "password": "davinci123"})


def _materia(nombre, carrera_id=1):
    return db.query_one("SELECT id FROM materias WHERE nombre = :n AND carrera_id = :c",
                        n=nombre, c=carrera_id)["id"]


@pytest.mark.parametrize("url", [
    "/admin/usuarios/",
    f"/admin/usuarios/{TOMAS}",
])
def test_un_estudiante_recibe_403_en_la_administracion(client, url):
    login(client, "mica@davinci.edu.ar")
    assert client.get(url).status_code == 403


@pytest.mark.parametrize(("url", "accion"), [
    (f"/admin/usuarios/{TOMAS}/bloqueo", "bloquear"),
    (f"/admin/usuarios/{TOMAS}/catedra", "nombrar"),
])
def test_un_estudiante_no_puede_bloquear_ni_nombrar_de_catedra(client, app, url, accion):
    login(client, "mica@davinci.edu.ar")
    assert client.post(url, data={"accion": accion, "motivo": "x"}).status_code == 403
    with app.app_context():
        assert not datos.obtener_usuario(TOMAS)["bloqueado"]
        assert not datos.obtener_usuario(TOMAS)["catedra"]


def test_sin_sesion_la_administracion_pide_ingresar(client):
    respuesta = client.get("/admin/usuarios/")
    assert respuesta.status_code == 302 and "/auth/login" in respuesta.headers["Location"]


def test_el_listado_busca_por_nombre_o_email_sin_acentos(client):
    login(client)
    texto = client.get("/admin/usuarios/?q=tomas").get_data(as_text=True)
    assert "Tomás Vega" in texto and "Mica Suárez" not in texto
    texto = client.get("/admin/usuarios/?q=LUCIA@").get_data(as_text=True)
    assert "Lucía Paz" in texto and "Tomás Vega" not in texto


def test_el_listado_filtra_por_carrera_rol_y_estado(app):
    with app.app_context():
        datos.cambiar_bloqueo(TOMAS, ADMIN, True, "Spam en el foro")
        assert {u["id"] for u in datos.listar_usuarios(carrera_id=1)} == {MICA, LUCIA}
        assert {u["id"] for u in datos.listar_usuarios(rol="admin")} == {ADMIN}
        assert {u["id"] for u in datos.listar_usuarios(rol="catedra")} == {LUCIA}
        assert {u["id"] for u in datos.listar_usuarios(estado="bloqueado")} == {TOMAS, BRUNO}
        assert TOMAS not in {u["id"] for u in datos.listar_usuarios(estado="activo")}


def test_bloquear_exige_motivo(app):
    with app.app_context(), pytest.raises(datos.ErrorUsuario, match="motivo"):
        datos.cambiar_bloqueo(TOMAS, ADMIN, True, "   ")


def test_un_admin_no_puede_bloquearse_a_si_mismo(client, app):
    with app.app_context(), pytest.raises(datos.ErrorUsuario, match="vos mismo"):
        datos.cambiar_bloqueo(ADMIN, ADMIN, True, "Prueba")
    login(client)
    client.post(f"/admin/usuarios/{ADMIN}/bloqueo", data={"accion": "bloquear", "motivo": "Prueba"})
    with app.app_context():
        assert not datos.obtener_usuario(ADMIN)["bloqueado"]


def test_bloqueo_y_desbloqueo_quedan_registrados(client, app):
    login(client)
    client.post(f"/admin/usuarios/{TOMAS}/bloqueo", data={"accion": "bloquear", "motivo": "Insultos en el chat"})
    client.post(f"/admin/usuarios/{TOMAS}/bloqueo", data={"accion": "desbloquear", "motivo": "Pidió disculpas"})
    with app.app_context():
        registros = datos.historial_bloqueos(TOMAS)
        assert not datos.obtener_usuario(TOMAS)["bloqueado"]
    assert [(r["accion"], r["motivo"], r["admin_id"]) for r in registros] == [
        ("desbloqueo", "Pidió disculpas", ADMIN),
        ("bloqueo", "Insultos en el chat", ADMIN),
    ]
    assert all(r["creado"] for r in registros)
    texto = client.get(f"/admin/usuarios/{TOMAS}").get_data(as_text=True)
    assert "Insultos en el chat" in texto and "Pidió disculpas" in texto


def test_no_se_bloquea_dos_veces(app):
    with app.app_context():
        datos.cambiar_bloqueo(TOMAS, ADMIN, True, "Spam")
        with pytest.raises(datos.ErrorUsuario, match="ya está bloqueado"):
            datos.cambiar_bloqueo(TOMAS, ADMIN, True, "Spam otra vez")
        assert len(datos.historial_bloqueos(TOMAS)) == 1


def test_al_bloquear_el_usuario_pierde_la_sesion_en_su_siguiente_accion(app):
    estudiante = app.test_client()
    login(estudiante, "tomas@davinci.edu.ar")
    assert estudiante.get("/reservas/mis-reservas/").status_code == 200
    with app.app_context():
        datos.cambiar_bloqueo(TOMAS, ADMIN, True, "Spam")
    respuesta = estudiante.get("/reservas/mis-reservas/")
    assert respuesta.status_code == 403
    assert "bloqueada" in respuesta.get_data(as_text=True)
    with estudiante.session_transaction() as sesion:
        assert "usuario_id" not in sesion
    with app.app_context():
        datos.cambiar_bloqueo(TOMAS, ADMIN, False, "Revisado")
    assert estudiante.get("/reservas/mis-reservas/").status_code == 302


def test_nombrar_de_catedra_avisa_al_estudiante(client, app):
    login(client)
    client.post(f"/admin/usuarios/{MICA}/catedra", data={"accion": "nombrar"})
    with app.app_context():
        assert datos.obtener_usuario(MICA)["catedra"]
        avisos = [a["cuerpo"] for a in db.query(
            "SELECT cuerpo FROM notificaciones WHERE usuario_id = :u AND cuerpo LIKE 'Ahora sos%'", u=MICA)]
    assert avisos == ["Ahora sos estudiante de cátedra de las materias que ya cursaste en Diseño Multimedial."]


def test_quitar_la_catedra(client, app):
    login(client)
    client.post(f"/admin/usuarios/{LUCIA}/catedra", data={"accion": "quitar"})
    with app.app_context():
        assert not datos.obtener_usuario(LUCIA)["catedra"]
        assert not datos.materias_con_catedra(datos.obtener_usuario(LUCIA))


def test_la_catedra_cubre_todas_las_materias_ya_cursadas(app):
    with app.app_context():
        datos.cambiar_catedra(MICA, True)
        materias = datos.materias_con_catedra(datos.obtener_usuario(MICA))
        primer_anio = db.query("SELECT id FROM materias WHERE carrera_id = 1 AND cuatrimestre <= 2")
    assert {m["id"] for m in materias} == {m["id"] for m in primer_anio}


def test_al_pasar_de_anio_la_catedra_suma_las_materias_nuevas(app):
    with app.app_context():
        datos.cambiar_catedra(MICA, True)
        antes = len(datos.materias_con_catedra(datos.obtener_usuario(MICA)))
        db.execute("UPDATE usuarios SET anio = 3 WHERE id = :id", id=MICA)
        despues = len(datos.materias_con_catedra(datos.obtener_usuario(MICA)))
    assert despues > antes


@pytest.mark.parametrize(("usuario", "preparar", "mensaje"), [
    (ADMIN, None, "estudiantes"),
    (TOMAS, None, "primer año"),
    (MICA, "sin_carrera", "carrera"),
    (LUCIA, None, "Ya es"),
])
def test_reglas_para_nombrar_de_catedra(app, usuario, preparar, mensaje):
    with app.app_context():
        if preparar == "sin_carrera":
            db.execute("UPDATE usuarios SET carrera_id = NULL WHERE id = :id", id=usuario)
        with pytest.raises(datos.ErrorUsuario, match=mensaje):
            datos.cambiar_catedra(usuario, True)


def test_el_estudiante_no_puede_pedirse_la_catedra(client, app):
    login(client, "mica@davinci.edu.ar")
    assert client.post(f"/admin/usuarios/{MICA}/catedra", data={"accion": "nombrar"}).status_code == 403
    with app.app_context():
        assert not datos.obtener_usuario(MICA)["catedra"]


def test_la_insignia_de_catedra_aparece_solo_en_las_materias_cursadas(app):
    plantilla = ('{% from "_persona.html" import insignia_catedra %}'
                 "[{{ insignia_catedra(usuario, materia) }}]")
    with app.test_request_context():
        cursada = _materia("Animación en 2D y 3D")
        sin_cursar = _materia("Proyecto Transmedia")
        de_otra_carrera = _materia("Elementos de Matemática", carrera_id=2)
        en_su_materia = render_template_string(plantilla, usuario=LUCIA, materia=cursada)
        en_una_que_cursa = render_template_string(plantilla, usuario=LUCIA, materia=sin_cursar)
        en_otra_carrera = render_template_string(plantilla, usuario=LUCIA, materia=de_otra_carrera)
        sin_catedra = render_template_string(plantilla, usuario=MICA, materia=_materia("Guión y Narrativa"))
    assert "Cátedra" in en_su_materia
    assert en_una_que_cursa == en_otra_carrera == sin_catedra == "[]"


def test_la_ficha_muestra_el_resumen_de_actividad(client):
    login(client)
    texto = client.get(f"/admin/usuarios/{TOMAS}").get_data(as_text=True)
    assert "Tomás Vega" in texto and "tomas@davinci.edu.ar" in texto
    for grupo in ("Foro", "Objetos", "Espacios y actividades", "Moderación"):
        assert grupo in texto


def test_resumen_de_actividad_cuenta_lo_del_usuario(app):
    with app.app_context():
        resumen = datos.resumen_actividad(TOMAS)
        propuestas = db.query_one("SELECT count(*) AS n FROM actividades WHERE creador_id = :u", u=TOMAS)["n"]
    assert resumen["actividades"] == propuestas
    assert set(resumen) >= {"reservas", "actividades", "inscripciones", "preguntas", "respuestas",
                            "publicaciones", "reportes"}


def test_ficha_de_usuario_inexistente_da_404(client):
    login(client)
    assert client.get("/admin/usuarios/99999").status_code == 404


def test_la_ficha_muestra_todo_el_plan_con_el_avance_del_estudiante(client):
    login(client)
    texto = client.get(f"/admin/usuarios/{MICA}").get_data(as_text=True)
    assert "3.er año" in texto
    assert texto.count('class="materia-cursada"') == 12
    assert texto.count('class="materia-cursando"') == 12
    assert 'class="materia-pendiente"' in texto


@pytest.fixture
def muchos_estudiantes(app):
    with app.app_context():
        for n in range(15):
            db.execute(
                "INSERT INTO usuarios (nombre, apellido, email, password_hash, carrera_id, anio, creado)"
                " VALUES (:n, 'Zúñiga', :e, 'x', 2, 1, '2026-10-18T00:00:00')",
                n=f"Estudiante{n:02d}", e=f"zuniga{n:02d}@davinci.edu.ar",
            )


def test_el_listado_trae_diez_por_pagina(app, muchos_estudiantes):
    with app.app_context():
        primera = datos.listar_usuarios(limite=10, salto=0)
        tercera = datos.listar_usuarios(limite=10, salto=20)
        assert len(primera) == 10 and len(tercera) == 1
        assert datos.contar_usuarios() == 21
        assert not {u["id"] for u in primera} & {u["id"] for u in tercera}


def test_la_paginacion_respeta_los_filtros(client, muchos_estudiantes):
    login(client)
    texto = client.get("/admin/usuarios/?q=zuniga").get_data(as_text=True)
    assert "<strong>15</strong> usuarios" in texto and "Página 1 de 2" in texto
    assert texto.count('class="fila-admin fila-usuario') == 10
    segunda = client.get("/admin/usuarios/?q=zuniga&pagina=2").get_data(as_text=True)
    assert segunda.count('class="fila-admin fila-usuario') == 5
    assert "q=zuniga" in segunda


def test_buscar_comodines_no_trae_a_todos(app):
    with app.app_context():
        assert datos.contar_usuarios(q="%") == 0
        assert datos.contar_usuarios(q="_") == 0
        assert datos.contar_usuarios(q="SUÁREZ") == 1
