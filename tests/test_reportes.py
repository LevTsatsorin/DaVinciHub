from davincihub import db
from davincihub.reportes import datos


def ingresar(client, email="mica@davinci.edu.ar"):
    return client.post("/auth/login", data={"email": email, "password": "davinci123"})


def ingresar_admin(client):
    return client.post("/auth/login", data={"email": "admin@davinci.edu.ar", "password": "davinci123"})


def test_perfil_muestra_boton_y_motivos(client):
    ingresar(client, "mica@davinci.edu.ar")
    res = client.get("/estudiantes/3")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # El botón reportar debe estar visible con la estética del sitio
    assert "reporte-detalles" in html
    assert "reporte-abrir" in html
    assert "¿Por qué reportás a este usuario?" in html

    # Todos los motivos deben estar como opciones en el select
    for motivo in datos.MOTIVOS:
        assert f'<option value="{motivo}">{motivo}</option>' in html


def test_no_puede_reportarse_a_si_mismo_en_perfil(client):
    ingresar(client, "mica@davinci.edu.ar")
    res = client.get("/estudiantes/2")
    html = res.get_data(as_text=True)
    # No debe mostrarse el botón de reporte en el propio perfil
    assert "¿Por qué reportás a este usuario?" not in html


def test_intento_reportarse_a_si_mismo_por_post(client, app):
    ingresar(client, "mica@davinci.edu.ar")
    res = client.post(
        "/reportes/crear",
        data={
            "tipo_objeto": "usuario",
            "objeto_id": "2",
            "motivo": datos.MOTIVOS[0],
            "siguiente": "/estudiantes/2",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "No podés reportarte a vos mismo" in html

    with app.app_context():
        assert not datos.ya_reporto(2, "usuario", 2)


def test_reportar_usuario_exitoso_y_evitar_duplicado(client, app):
    ingresar(client, "mica@davinci.edu.ar")

    # Primer reporte
    res = client.post(
        "/reportes/crear",
        data={
            "tipo_objeto": "usuario",
            "objeto_id": "3",
            "motivo": "Acoso o discriminación",
            "siguiente": "/estudiantes/3",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Gracias por tu reporte" in html

    with app.app_context():
        assert datos.ya_reporto(2, "usuario", 3)
        reporte = db.query_one(
            "SELECT * FROM reportes WHERE autor_id = 2 AND tipo_objeto = 'usuario' AND objeto_id = 3"
        )
        assert reporte is not None
        assert reporte["motivo"] == "Acoso o discriminación"
        assert reporte["estado"] == "pendiente"

    # Segundo reporte duplicado
    res2 = client.post(
        "/reportes/crear",
        data={
            "tipo_objeto": "usuario",
            "objeto_id": "3",
            "motivo": "Spam o publicidad no permitida",
            "siguiente": "/estudiantes/3",
        },
        follow_redirects=True,
    )
    assert res2.status_code == 200
    html2 = res2.get_data(as_text=True)
    assert "Ya reportaste a este usuario" in html2


def test_motivo_invalido_rechazado(client, app):
    ingresar(client, "mica@davinci.edu.ar")
    res = client.post(
        "/reportes/crear",
        data={
            "tipo_objeto": "usuario",
            "objeto_id": "4",
            "motivo": "Motivo inexistente que inventé",
            "siguiente": "/estudiantes/4",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Elegí un motivo válido" in html


def test_admin_cola_acceso_directo_al_contenido(client, app):
    # Creamos un reporte para una publicación y una respuesta del foro
    with app.app_context():
        pub = db.query_one("SELECT id, titulo FROM publicaciones LIMIT 1")
        resp = db.query_one("SELECT id, pregunta_id FROM respuestas LIMIT 1")
        datos.crear_reporte(2, "publicacion", pub["id"], "Spam o publicidad no permitida")
        datos.crear_reporte(2, "respuesta", resp["id"], "Contenido inapropiado u ofensivo")

    ingresar_admin(client)
    res = client.get("/reportes/admin")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Verificamos acceso directo al contenido
    assert f"/objetos/{pub['id']}" in html
    assert f"/foro/{resp['pregunta_id']}#respuesta-{resp['id']}" in html
    assert "Ver contenido ↗" in html


def test_admin_descarta_reporte_dejando_motivo(client, app):
    with app.app_context():
        pub = db.query_one("SELECT id FROM publicaciones LIMIT 1")
        r_id = datos.crear_reporte(2, "publicacion", pub["id"], "Otro")

    ingresar_admin(client)
    res = client.post(
        f"/reportes/{r_id}/resolver",
        data={
            "accion": "descartar",
            "resolucion": "El contenido respeta las pautas comunitarias.",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert "Reporte descartado" in res.get_data(as_text=True)

    with app.app_context():
        reporte = datos.obtener_reporte(r_id)
        assert reporte["estado"] == "resuelto"
        assert reporte["resolucion"] == "El contenido respeta las pautas comunitarias."
        # No se oculta el contenido
        pub_db = db.query_one("SELECT oculto FROM publicaciones WHERE id = :id", id=pub["id"])
        assert pub_db["oculto"] == 0


def test_admin_oculta_contenido_dejando_motivo(client, app):
    with app.app_context():
        pub = db.query_one("SELECT id FROM publicaciones WHERE oculto = 0 LIMIT 1")
        r_id = datos.crear_reporte(2, "publicacion", pub["id"], "Contenido inapropiado u ofensivo")

    ingresar_admin(client)
    res = client.post(
        f"/reportes/{r_id}/resolver",
        data={
            "accion": "ocultar",
            "resolucion": "Lenguaje inapropiado en la descripción.",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert "Contenido ocultado" in res.get_data(as_text=True)

    with app.app_context():
        reporte = datos.obtener_reporte(r_id)
        assert reporte["estado"] == "resuelto"
        assert reporte["resolucion"] == "Lenguaje inapropiado en la descripción."
        # El contenido quedó oculto
        pub_db = db.query_one("SELECT oculto FROM publicaciones WHERE id = :id", id=pub["id"])
        assert pub_db["oculto"] == 1


def test_admin_deriva_a_bloqueo_a7_dejando_motivo(client, app):
    with app.app_context():
        # Reportamos al usuario Tomás (id 3)
        r_id = datos.crear_reporte(2, "usuario", 3, "Acoso o discriminación")

    ingresar_admin(client)
    # Resolver derivando a bloqueo
    res = client.post(
        f"/reportes/{r_id}/resolver",
        data={
            "accion": "bloquear",
            "resolucion": "Reiteradas faltas de respeto hacia compañeros.",
        },
        follow_redirects=False,
    )
    # Redirige a la ficha del usuario para completar el bloqueo con el motivo en query
    assert res.status_code == 302
    assert "/admin/usuarios/3" in res.headers["Location"]
    assert "motivo=Reiteradas+faltas+de+respeto" in res.headers["Location"]

    # Seguimos la redirección a la ficha del usuario
    res_ficha = client.get(res.headers["Location"])
    assert res_ficha.status_code == 200
    assert "Reiteradas faltas de respeto" in res_ficha.get_data(as_text=True)

    # El reporte quedó resuelto con la derivación
    with app.app_context():
        reporte = datos.obtener_reporte(r_id)
        assert reporte["estado"] == "resuelto"
        assert "Derivado a bloqueo" in reporte["resolucion"]

    # Completar el bloqueo en la ficha (flujo A7)
    res_bloqueo = client.post(
        "/admin/usuarios/3/bloqueo",
        data={
            "accion": "bloquear",
            "motivo": "Reiteradas faltas de respeto hacia compañeros.",
        },
        follow_redirects=True,
    )
    assert res_bloqueo.status_code == 200
    assert "Cuenta bloqueada" in res_bloqueo.get_data(as_text=True)

    with app.app_context():
        usuario_db = db.query_one("SELECT bloqueado FROM usuarios WHERE id = 3")
        assert usuario_db["bloqueado"] == 1
        bloqueo_reg = db.query_one("SELECT * FROM bloqueos WHERE usuario_id = 3")
        assert bloqueo_reg is not None
        assert bloqueo_reg["motivo"] == "Reiteradas faltas de respeto hacia compañeros."


def test_resolver_sin_motivo_falla(client, app):
    with app.app_context():
        pub = db.query_one("SELECT id FROM publicaciones LIMIT 1")
        r_id = datos.crear_reporte(2, "publicacion", pub["id"], "Otro")

    ingresar_admin(client)
    res = client.post(
        f"/reportes/{r_id}/resolver",
        data={
            "accion": "descartar",
            "resolucion": "   ",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert "Escribí el motivo de la resolución" in res.get_data(as_text=True)

    with app.app_context():
        reporte = datos.obtener_reporte(r_id)
        assert reporte["estado"] == "pendiente"
