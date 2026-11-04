from io import BytesIO

from davincihub import db


def ingresar(client, email="mica@davinci.edu.ar"):
    return client.post("/auth/login", data={"email": email, "password": "davinci123"})


def usuario_id(app, email):
    with app.app_context():
        return db.query_one("SELECT id FROM usuarios WHERE email = :email", email=email)["id"]


def materia_id(app, nombre, carrera_id=1):
    with app.app_context():
        return db.query_one(
            "SELECT id FROM materias WHERE nombre = :nombre AND carrera_id = :carrera",
            nombre=nombre,
            carrera=carrera_id,
        )["id"]


def crear_pregunta(app, autor_id=2, materia=1, titulo="Duda de prueba"):
    with app.app_context():
        return db.query_one(
            "INSERT INTO preguntas (autor_id, materia_id, titulo, cuerpo, creado)"
            " VALUES (:autor, :materia, :titulo, 'Descripción de prueba', '2026-10-20T12:00:00')"
            " RETURNING id",
            autor=autor_id,
            materia=materia,
            titulo=titulo,
        )["id"]


def crear_respuesta(app, pregunta_id, autor_id, cuerpo="Respuesta de prueba", aceptada=0):
    with app.app_context():
        return db.query_one(
            "INSERT INTO respuestas (pregunta_id, autor_id, cuerpo, aceptada, creado)"
            " VALUES (:pregunta, :autor, :cuerpo, :aceptada, '2026-10-20T12:10:00') RETURNING id",
            pregunta=pregunta_id,
            autor=autor_id,
            cuerpo=cuerpo,
            aceptada=aceptada,
        )["id"]


def test_foro_guia_a_login_y_no_expone_preguntas(client, app):
    crear_pregunta(app, titulo="Pregunta privada")
    contenido = client.get("/foro/").get_data(as_text=True)
    assert "Iniciá sesión para ver el foro" in contenido
    assert "Pregunta privada" not in contenido
    assert client.get("/foro/preguntas/1").status_code == 302


def test_publicar_pregunta_muestra_materia_carrera_y_respuestas(client, app):
    ingresar(client)
    respuesta = client.post(
        "/foro/preguntas/nueva",
        data={
            "carrera_id": "1",
            "materia_id": str(materia_id(app, "Lógica de la Programación")),
            "titulo": "¿Cómo resuelvo este ejercicio?",
            "cuerpo": "Necesito una orientación.",
        },
    )
    assert respuesta.status_code == 302
    lista = client.get("/foro/").get_data(as_text=True)
    assert "¿Cómo resuelvo este ejercicio?" in lista
    assert "Lógica de la Programación" in lista
    assert "Sin responder" in lista


def test_detalle_enlaza_nombres_a_perfiles_y_muestra_carrera(client, app):
    pregunta_id = crear_pregunta(app)
    respuesta_id = crear_respuesta(app, pregunta_id, usuario_id(app, "tomas@davinci.edu.ar"))
    ingresar(client)

    contenido = client.get(f"/foro/preguntas/{pregunta_id}").get_data(as_text=True)

    assert 'href="/estudiantes/2"' in contenido
    assert "Diseño Multimedial" in contenido
    assert f'href="/estudiantes/{usuario_id(app, "tomas@davinci.edu.ar")}"' in contenido
    assert str(respuesta_id) in contenido


def test_busqueda_filtra_materia_carrera_y_texto_y_limpiar_muestra_todo(client, app):
    logica = materia_id(app, "Lógica de la Programación")
    crear_pregunta(app, materia=logica, titulo="Algoritmos y estructuras de datos")
    crear_pregunta(app, titulo="Diseño de una interfaz accesible")
    ingresar(client)

    logica = client.get("/foro/?q=logica").get_data(as_text=True)
    assert "Algoritmos y estructuras de datos" in logica
    assert "Diseño de una interfaz accesible" not in logica
    carrera = client.get("/foro/?q=Multimedial").get_data(as_text=True)
    assert "Algoritmos y estructuras de datos" in carrera
    texto = client.get("/foro/?q=interfaz").get_data(as_text=True)
    assert "Diseño de una interfaz accesible" in texto
    assert "Algoritmos y estructuras de datos" not in texto
    todas = client.get("/foro/").get_data(as_text=True)
    assert "Algoritmos y estructuras de datos" in todas
    assert "Diseño de una interfaz accesible" in todas


def test_filtros_desplegables_de_carrera_y_materia(client, app):
    materia_dm = materia_id(app, "Lógica de la Programación", 1)
    materia_videojuegos = materia_id(app, "Lógica de la Programación", 2)
    crear_pregunta(app, materia=materia_dm, titulo="Consulta de Diseño Multimedial")
    crear_pregunta(app, materia=materia_videojuegos, titulo="Consulta de Videojuegos")
    ingresar(client)

    carrera = client.get("/foro/?carrera_id=1").get_data(as_text=True)
    assert "Consulta de Diseño Multimedial" in carrera
    assert "Consulta de Videojuegos" not in carrera
    materia = client.get(f"/foro/?materia_id={materia_videojuegos}").get_data(as_text=True)
    assert "Consulta de Videojuegos" in materia
    assert "Consulta de Diseño Multimedial" not in materia
    combinados = client.get(
        f"/foro/?q=Consulta&carrera_id=2&materia_id={materia_videojuegos}"
    ).get_data(as_text=True)
    assert "Consulta de Videojuegos" in combinados
    assert "Consulta de Diseño Multimedial" not in combinados
    assert 'name="carrera_id"' in combinados
    assert 'name="materia_id"' in combinados


def test_mis_dudas_muestra_solo_preguntas_del_usuario_autenticado(client, app):
    propia = crear_pregunta(app, autor_id=usuario_id(app, "mica@davinci.edu.ar"), titulo="Mi pregunta personal")
    crear_pregunta(app, autor_id=usuario_id(app, "tomas@davinci.edu.ar"), titulo="Pregunta de otra persona")
    ingresar(client)

    contenido = client.get("/foro/?mis_dudas=1").get_data(as_text=True)
    assert "Mi pregunta personal" in contenido
    assert "Pregunta de otra persona" not in contenido
    assert f'href="/foro/preguntas/{propia}"' in contenido
    assert "mis_dudas=1" in contenido


def test_titulo_y_descripcion_de_pregunta_requieren_diez_caracteres(client, app):
    ingresar(client)
    respuesta = client.post(
        "/foro/preguntas/nueva",
        data={
            "carrera_id": "1",
            "materia_id": str(materia_id(app, "Lógica de la Programación")),
            "titulo": "corto",
            "cuerpo": "descripción válida",
        },
    )
    assert respuesta.status_code == 200
    assert "título debe tener al menos 10 caracteres" in respuesta.get_data(as_text=True)

    respuesta = client.post(
        "/foro/preguntas/nueva",
        data={
            "carrera_id": "1",
            "materia_id": str(materia_id(app, "Lógica de la Programación")),
            "titulo": "Un título suficientemente largo",
            "cuerpo": "corta",
        },
    )
    assert respuesta.status_code == 200
    assert "descripción debe tener al menos 10 caracteres" in respuesta.get_data(as_text=True)


def test_pregunta_admite_imagen_y_solo_usuarios_logueados_pueden_verla(client, app):
    ingresar(client)
    imagen_png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
    )
    respuesta = client.post(
        "/foro/preguntas/nueva",
        data={
            "carrera_id": "1",
            "materia_id": str(materia_id(app, "Lógica de la Programación")),
            "titulo": "Duda con una imagen de referencia",
            "cuerpo": "Adjunto esta imagen para explicar mi duda.",
            "imagen": (BytesIO(imagen_png), "duda.png"),
        },
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 302
    url_imagen = f"{respuesta.headers['Location']}/imagen"
    descarga = client.get(url_imagen)
    assert descarga.data == imagen_png
    assert descarga.mimetype == "image/png"
    client.post("/auth/salir")
    assert client.get(url_imagen).status_code == 302


def test_imagen_rechaza_contenido_que_no_sea_imagen(client, app):
    ingresar(client)
    respuesta = client.post(
        "/foro/preguntas/nueva",
        data={
            "carrera_id": "1",
            "materia_id": str(materia_id(app, "Lógica de la Programación")),
            "titulo": "Duda con una imagen de referencia",
            "cuerpo": "Adjunto esta imagen para explicar mi duda.",
            "imagen": (BytesIO(b"<script>alert(1)</script>"), "duda.png"),
        },
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 200
    assert "Usá una imagen PNG, JPG, GIF o WebP válida" in respuesta.get_data(as_text=True)


def test_no_se_puede_asociar_materia_a_otra_carrera(client):
    ingresar(client)
    respuesta = client.post(
        "/foro/preguntas/nueva",
        data={
            "carrera_id": "2",
            "materia_id": str(materia_id(client.application, "Lógica de la Programación")),
            "titulo": "Duda de programación",
            "cuerpo": "Descripción de la pregunta",
        },
    )
    assert respuesta.status_code == 200
    assert "no corresponde a la carrera seleccionada" in respuesta.get_data(as_text=True)


def test_solo_autor_edita_pregunta_y_la_edicion_se_bloquea_al_aceptar(client, app):
    pregunta_id = crear_pregunta(app)
    ingresar(client, "tomas@davinci.edu.ar")
    assert client.post(
        f"/foro/preguntas/{pregunta_id}/editar",
        data={"carrera_id": "1", "materia_id": "1", "titulo": "Alterada", "cuerpo": "Alterada"},
    ).status_code == 403

    client.post("/auth/salir")
    ingresar(client)
    editar = {
        "carrera_id": "1",
        "materia_id": "1",
        "titulo": "Pregunta editada",
        "cuerpo": "Descripción nueva",
    }
    assert client.post(f"/foro/preguntas/{pregunta_id}/editar", data=editar).status_code == 302
    respuesta_id = crear_respuesta(app, pregunta_id, usuario_id(app, "tomas@davinci.edu.ar"))
    assert client.post(
        f"/foro/respuestas/{respuesta_id}/aceptar", data={"aceptada": "1"}
    ).status_code == 302
    bloqueada = client.post(
        f"/foro/preguntas/{pregunta_id}/editar",
        data={**editar, "titulo": "No se debe guardar"},
    )
    assert bloqueada.status_code == 200
    assert "después de aceptar una respuesta" in bloqueada.get_data(as_text=True)


def test_aceptar_reemplazar_quitar_y_notificar(client, app):
    pregunta_id = crear_pregunta(app)
    primera = crear_respuesta(app, pregunta_id, usuario_id(app, "tomas@davinci.edu.ar"), "Primera")
    segunda = crear_respuesta(app, pregunta_id, usuario_id(app, "lucia@davinci.edu.ar"), "Segunda")
    ingresar(client)

    assert client.post(f"/foro/respuestas/{primera}/aceptar", data={"aceptada": "1"}).status_code == 302
    assert client.post(f"/foro/respuestas/{primera}/aceptar", data={"aceptada": "1"}).status_code == 302
    assert client.post(f"/foro/respuestas/{segunda}/aceptar", data={"aceptada": "1"}).status_code == 302
    with app.app_context():
        aceptadas = db.query("SELECT id FROM respuestas WHERE pregunta_id = :id AND aceptada = 1", id=pregunta_id)
        avisos = db.query(
            "SELECT usuario_id FROM notificaciones WHERE tipo = 'foro' AND cuerpo = 'Tu respuesta fue aceptada.'"
        )
    assert aceptadas == [{"id": segunda}]
    assert {aviso["usuario_id"] for aviso in avisos} == {
        usuario_id(app, "tomas@davinci.edu.ar"),
        usuario_id(app, "lucia@davinci.edu.ar"),
    }

    detalle = client.get(f"/foro/preguntas/{pregunta_id}").get_data(as_text=True)
    assert detalle.index("Respuesta aceptada") < detalle.index("Primera")
    assert "¿Estás seguro de que querés quitar esta respuesta aceptada?" in detalle
    assert "data-confirmar-tono=\"peligro\"" in detalle
    assert client.post(f"/foro/respuestas/{segunda}/aceptar", data={"aceptada": "0"}).status_code == 302
    with app.app_context():
        assert db.query_one(
            "SELECT COUNT(*) AS n FROM respuestas WHERE pregunta_id = :id AND aceptada = 1",
            id=pregunta_id,
        )["n"] == 0


def test_aceptacion_solo_por_autor_de_pregunta(client, app):
    pregunta_id = crear_pregunta(app)
    respuesta_id = crear_respuesta(app, pregunta_id, usuario_id(app, "lucia@davinci.edu.ar"))
    ingresar(client, "tomas@davinci.edu.ar")
    assert client.post(
        f"/foro/respuestas/{respuesta_id}/aceptar", data={"aceptada": "1"}
    ).status_code == 403


def test_autor_de_pregunta_no_puede_aceptar_su_propia_respuesta(client, app):
    pregunta_id = crear_pregunta(app)
    respuesta_id = crear_respuesta(app, pregunta_id, usuario_id(app, "mica@davinci.edu.ar"))
    ingresar(client)
    assert client.post(
        f"/foro/respuestas/{respuesta_id}/aceptar", data={"aceptada": "1"}
    ).status_code == 403
    detalle = client.get(f"/foro/preguntas/{pregunta_id}").get_data(as_text=True)
    assert "Aceptar respuesta" not in detalle


def test_no_se_puede_aceptar_una_respuesta_anidada(client, app):
    pregunta_id = crear_pregunta(app)
    principal = crear_respuesta(app, pregunta_id, usuario_id(app, "tomas@davinci.edu.ar"))
    with app.app_context():
        anidada = db.query_one(
            "INSERT INTO respuestas (pregunta_id, autor_id, cuerpo, creado, respuesta_padre_id)"
            " VALUES (:pregunta, :autor, 'Respuesta complementaria', '2026-10-20T12:20:00', :padre)"
            " RETURNING id",
            pregunta=pregunta_id,
            autor=usuario_id(app, "lucia@davinci.edu.ar"),
            padre=principal,
        )["id"]
    ingresar(client)

    respuesta = client.post(
        f"/foro/respuestas/{anidada}/aceptar",
        data={"aceptada": "1"},
        follow_redirects=True,
    )

    assert "Solo podés aceptar una respuesta principal." in respuesta.get_data(as_text=True)
    with app.app_context():
        assert db.query_one(
            "SELECT COUNT(*) AS n FROM respuestas WHERE pregunta_id = :id AND aceptada = 1",
            id=pregunta_id,
        )["n"] == 0


def test_responder_comentario_notifica_al_autor_y_no_admite_respuesta_propia(client, app):
    pregunta_id = crear_pregunta(app)
    parent_id = crear_respuesta(app, pregunta_id, usuario_id(app, "tomas@davinci.edu.ar"))
    ingresar(client)
    respuesta = client.post(
        f"/foro/respuestas/{parent_id}/responder",
        data={"cuerpo": "Te respondo con más detalle."},
    )
    assert respuesta.status_code == 302
    contenido = client.get(f"/foro/preguntas/{pregunta_id}").get_data(as_text=True)
    assert "Te respondo con más detalle." in contenido
    assert "Ver respuestas (1) o responder" in contenido
    assert 'class="foro-subcomentario-cabecera"' in contenido
    assert "Mica Suárez" in contenido
    assert "<time datetime=" in contenido
    with app.app_context():
        notificacion = db.query_one(
            "SELECT cuerpo FROM notificaciones WHERE usuario_id = :id"
            " AND cuerpo LIKE '%respondió tu comentario%'",
            id=usuario_id(app, "tomas@davinci.edu.ar"),
        )
        hija = db.query_one(
            "SELECT id FROM respuestas WHERE respuesta_padre_id = :id",
            id=parent_id,
        )
    assert notificacion is not None

    client.post("/auth/salir")
    ingresar(client, "tomas@davinci.edu.ar")
    assert client.post(
        f"/foro/respuestas/{parent_id}/responder",
        data={"cuerpo": "No puedo responder mi propio comentario."},
    ).status_code == 403
    client.post("/auth/salir")
    ingresar(client)
    assert client.post(
        f"/foro/respuestas/{hija['id']}/responder",
        data={"cuerpo": "Tampoco puedo auto responder."},
    ).status_code == 403


def test_responder_la_pregunta_notifica_a_su_autor(client, app):
    pregunta_id = crear_pregunta(app)
    ingresar(client, "tomas@davinci.edu.ar")
    respuesta = client.post(
        f"/foro/preguntas/{pregunta_id}/responder",
        data={"cuerpo": "Acá va una explicación detallada."},
    )
    assert respuesta.status_code == 302
    with app.app_context():
        notificacion = db.query_one(
            "SELECT cuerpo FROM notificaciones WHERE usuario_id = :id"
            " AND cuerpo LIKE '%respondió tu pregunta%'",
            id=usuario_id(app, "mica@davinci.edu.ar"),
        )
    assert notificacion is not None


def test_valoracion_unica_no_propia_y_notificacion_sin_duplicados(client, app):
    pregunta_id = crear_pregunta(app)
    respuesta_id = crear_respuesta(app, pregunta_id, usuario_id(app, "tomas@davinci.edu.ar"))
    ingresar(client)
    assert client.post(f"/foro/respuestas/{respuesta_id}/util").status_code == 302
    assert client.post(f"/foro/respuestas/{respuesta_id}/util").status_code == 302
    detalle = client.get(f"/foro/preguntas/{pregunta_id}").get_data(as_text=True)
    assert "Útil <strong>1</strong>" in detalle
    with app.app_context():
        assert db.query_one(
            "SELECT COUNT(*) AS n FROM valoraciones_respuestas WHERE respuesta_id = :id",
            id=respuesta_id,
        )["n"] == 1
        assert db.query_one(
            "SELECT COUNT(*) AS n FROM notificaciones WHERE usuario_id = :id"
            " AND cuerpo = 'Alguien marcó tu respuesta como útil.'",
            id=usuario_id(app, "tomas@davinci.edu.ar"),
        )["n"] == 1

    client.post("/auth/salir")
    ingresar(client, "tomas@davinci.edu.ar")
    assert client.post(f"/foro/respuestas/{respuesta_id}/util").status_code == 403


def test_edicion_respuesta_se_bloquea_cuando_hay_aceptada(client, app):
    pregunta_id = crear_pregunta(app)
    respuesta_id = crear_respuesta(app, pregunta_id, usuario_id(app, "tomas@davinci.edu.ar"))
    ingresar(client, "tomas@davinci.edu.ar")
    assert client.post(
        f"/foro/respuestas/{respuesta_id}/editar", data={"cuerpo": "Editada"}
    ).status_code == 302

    client.post("/auth/salir")
    ingresar(client)
    client.post(f"/foro/respuestas/{respuesta_id}/aceptar", data={"aceptada": "1"})
    client.post("/auth/salir")
    ingresar(client, "tomas@davinci.edu.ar")
    respuesta = client.post(
        f"/foro/respuestas/{respuesta_id}/editar", data={"cuerpo": "No guardar"}
    )
    assert respuesta.status_code == 200
    assert "después de aceptar una" in respuesta.get_data(as_text=True)


def test_insignia_catedra_solo_en_materias_asignadas(client, app):
    carrera_misma = materia_id(app, "Lógica de la Programación", 1)
    carrera_otra = materia_id(app, "Lógica de la Programación", 2)
    pregunta_misma = crear_pregunta(app, materia=carrera_misma, titulo="Materia de cátedra")
    pregunta_otra = crear_pregunta(app, materia=carrera_otra, titulo="Otra carrera")
    lucia = usuario_id(app, "lucia@davinci.edu.ar")
    crear_respuesta(app, pregunta_misma, lucia, "Acompañamiento de cátedra")
    crear_respuesta(app, pregunta_otra, lucia, "Sin insignia en esta carrera")
    ingresar(client)

    propia = client.get(f"/foro/preguntas/{pregunta_misma}").get_data(as_text=True)
    ajena = client.get(f"/foro/preguntas/{pregunta_otra}").get_data(as_text=True)
    assert "Cátedra · Lógica de la Programación" in propia
    assert "Cátedra · Lógica de la Programación" not in ajena


def test_respuesta_en_hilo_tambien_avisa_al_autor_de_la_pregunta(client, app):
    pregunta_id = crear_pregunta(app)
    padre_id = crear_respuesta(app, pregunta_id, usuario_id(app, "tomas@davinci.edu.ar"))
    ingresar(client, "lucia@davinci.edu.ar")
    client.post(f"/foro/respuestas/{padre_id}/responder", data={"cuerpo": "Sumo un dato al hilo."})
    with app.app_context():
        avisos = db.query(
            "SELECT usuario_id FROM notificaciones WHERE tipo = 'foro' ORDER BY usuario_id"
        )
    assert [a["usuario_id"] for a in avisos] == [2, usuario_id(app, "tomas@davinci.edu.ar")]


def test_filtro_por_cuatrimestre(client, app):
    with app.app_context():
        primera = db.query_one("SELECT id FROM materias WHERE carrera_id = 1 AND cuatrimestre = 1 LIMIT 1")["id"]
        segunda = db.query_one("SELECT id FROM materias WHERE carrera_id = 1 AND cuatrimestre = 2 LIMIT 1")["id"]
    crear_pregunta(app, materia=primera, titulo="Duda del primer cuatri")
    crear_pregunta(app, materia=segunda, titulo="Duda del segundo cuatri")
    ingresar(client)
    contenido = client.get("/foro/?cuatrimestre=2").get_data(as_text=True)
    assert "Duda del segundo cuatri" in contenido
    assert "Duda del primer cuatri" not in contenido
    assert 'name="cuatrimestre"' in contenido


def test_no_se_publica_en_materia_o_carrera_deshabilitada(client, app):
    ingresar(client)
    datos_pregunta = {"carrera_id": "1", "materia_id": "1",
                      "titulo": "Pregunta en materia cerrada", "cuerpo": "Detalle suficiente de la duda."}
    with app.app_context():
        db.execute("UPDATE materias SET activa = 0 WHERE id = 1")
    assert client.post("/foro/preguntas/nueva", data=datos_pregunta).status_code == 200
    with app.app_context():
        db.execute("UPDATE materias SET activa = 1 WHERE id = 1")
        db.execute("UPDATE carreras SET activa = 0 WHERE id = 1")
    assert client.post("/foro/preguntas/nueva", data=datos_pregunta).status_code == 200
    with app.app_context():
        assert db.query_one(
            "SELECT count(*) AS n FROM preguntas WHERE titulo = 'Pregunta en materia cerrada'"
        )["n"] == 0


def test_formularios_de_edicion_no_abren_con_respuesta_aceptada(client, app):
    pregunta_id = crear_pregunta(app)
    respuesta_id = crear_respuesta(app, pregunta_id, usuario_id(app, "tomas@davinci.edu.ar"), aceptada=1)
    ingresar(client)
    assert client.get(f"/foro/preguntas/{pregunta_id}/editar").headers["Location"] == f"/foro/preguntas/{pregunta_id}"
    client.post("/auth/salir")
    ingresar(client, "tomas@davinci.edu.ar")
    assert client.get(f"/foro/respuestas/{respuesta_id}/editar").headers["Location"] == f"/foro/preguntas/{pregunta_id}"


def test_respuesta_anidada_tiene_enlace_para_editar(client, app):
    pregunta_id = crear_pregunta(app)
    padre_id = crear_respuesta(app, pregunta_id, usuario_id(app, "tomas@davinci.edu.ar"))
    ingresar(client, "lucia@davinci.edu.ar")
    client.post(f"/foro/respuestas/{padre_id}/responder", data={"cuerpo": "Respuesta en el hilo."})
    with app.app_context():
        hija = db.query_one("SELECT id FROM respuestas WHERE respuesta_padre_id = :id", id=padre_id)["id"]
    assert f"/foro/respuestas/{hija}/editar" in client.get(f"/foro/preguntas/{pregunta_id}").get_data(as_text=True)


def test_caracteres_invisibles_no_cuentan_como_texto(client):
    ingresar(client)
    invisible = "\u200b" * 12
    respuesta = client.post("/foro/preguntas/nueva", data={
        "carrera_id": "1", "materia_id": "1", "titulo": invisible, "cuerpo": invisible,
    })
    assert respuesta.status_code == 200


def test_cabecera_del_foro_sin_sesion_tiene_html_balanceado(client):
    contenido = client.get("/foro/").get_data(as_text=True)
    cabecera = contenido.split('class="cabecera-seccion fondo-oscuro"', 1)[1].split("</section>", 1)[0]
    assert cabecera.count("<div") == cabecera.count("</div>")


def test_confirmacion_para_aceptar_y_edicion_de_pregunta_debajo_de_imagen(client, app):
    pregunta_id = crear_pregunta(app)
    respuesta_id = crear_respuesta(app, pregunta_id, usuario_id(app, "tomas@davinci.edu.ar"))
    with app.app_context():
        db.execute(
            "UPDATE preguntas SET imagen_tipo = 'image/png', imagen = :imagen WHERE id = :id",
            imagen=b"imagen",
            id=pregunta_id,
        )
    ingresar(client)

    contenido = client.get(f"/foro/preguntas/{pregunta_id}").get_data(as_text=True)

    assert "¿Estás seguro de que querés aceptar esta respuesta?" in contenido
    assert 'data-confirmar-tono="positivo"' in contenido
    assert contenido.index("foro-imagen-adjunta") < contenido.index("foro-editar-pregunta")
    assert 'action="/foro/respuestas/' + str(respuesta_id) + '/aceptar"' in contenido
