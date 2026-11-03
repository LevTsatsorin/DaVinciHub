import pytest

from davincihub import db, reputacion, reputacion_demo
from davincihub.objetos import acuerdos, datos


@pytest.fixture(params=["prestamo", "intercambio", "venta"])
def operacion(app, request):
    tipo = request.param
    with app.app_context():
        pid = datos.crear(3, {
            "titulo": "Material de estudio", "descripcion": "En buen estado",
            "categoria": "dibujo_diseno", "estado_objeto": "usado_buen_estado",
            "modalidad": tipo, "precio": "1000", "carrera_id": "",
        })
        if tipo == "prestamo":
            fila = db.query_one(
                "INSERT INTO prestamos (publicacion_id, solicitante_id, fecha_entrega,"
                " fecha_devolucion, creado) VALUES (:p, 2, '2026-01-01', '2026-01-02',"
                " '2026-01-01') RETURNING id", p=pid,
            )
            oid = fila["id"]
        else:
            _, oid = acuerdos.proponer(pid, 2, {"oferta": "Un libro", "precio_acordado": "1000"})
    return tipo, oid


def finalizar(tipo, oid):
    if tipo == "prestamo":
        db.execute("UPDATE prestamos SET estado = 'devuelto' WHERE id = :id", id=oid)
    else:
        acuerdos.cambiar(tipo, oid, 3, "aceptar")
        acuerdos.cambiar(tipo, oid, 2, "confirmar")
        acuerdos.cambiar(tipo, oid, 3, "confirmar")


def test_solo_finalizadas_y_participantes(app, operacion):
    tipo, oid = operacion
    with app.app_context():
        with pytest.raises(ValueError):
            reputacion.valorar(tipo, oid, 2, {"valor": "5"})
        finalizar(tipo, oid)
        with pytest.raises(PermissionError):
            reputacion.valorar(tipo, oid, 4, {"valor": "5"})
        assert not db.query("SELECT * FROM valoraciones_operaciones")


def test_ambas_partes_una_vez_y_perfil(app, client, operacion):
    tipo, oid = operacion
    with app.app_context():
        finalizar(tipo, oid)
        reputacion.valorar(tipo, oid, 2, {"valor": "5", "comentario": "Muy buena experiencia"})
        reputacion.valorar(tipo, oid, 3, {"valor": "3"})
        with pytest.raises(ValueError):
            reputacion.valorar(tipo, oid, 2, {"valor": "1"})
        assert reputacion.propia(tipo, oid, 2)["valor"] == 5
    pagina = client.get("/estudiantes/3")
    assert pagina.status_code == 200
    assert "Muy buena experiencia" in pagina.text
    assert "1 opinión" in pagina.text
    assert "reputacion-estrella" in pagina.text
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = 2
    ruta = f"/objetos/prestamos/{oid}" if tipo == "prestamo" else f"/objetos/acuerdos/{tipo}/{oid}"
    assert "Ya valoraste esta operación" in client.get(ruta).text


@pytest.mark.parametrize("form", [{"valor": "0"}, {"valor": "6"}, {"valor": "2.5"},
                                   {"valor": "5", "comentario": "a" * 2001}])
def test_valida_puntuacion_y_comentario(app, operacion, form):
    with app.app_context():
        finalizar(*operacion)
        with pytest.raises(ValueError):
            reputacion.valorar(*operacion, 2, form)


def test_ruta_deriva_receptor_y_exige_login(app, client, operacion):
    tipo, oid = operacion
    ruta = f"/reputacion/{tipo}/{oid}"
    assert client.post(ruta, data={"valor": "5"}).status_code == 302
    with app.app_context():
        finalizar(tipo, oid)
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = 2
    assert client.post(ruta, data={"valor": "4", "receptor_id": "2"}).status_code == 302
    with app.app_context():
        fila = db.query_one("SELECT * FROM valoraciones_operaciones")
        assert fila["autor_id"] == 2 and fila["receptor_id"] == 3
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = 4
    assert client.post(ruta, data={"valor": "5"}).status_code == 403


def test_perfil_muestra_dos_recientes_y_enlace_al_historial(app, client):
    with app.app_context():
        for numero in range(3):
            pid = datos.crear(3, {
                "titulo": f"Material {numero}", "descripcion": "En buen estado",
                "categoria": "dibujo_diseno", "estado_objeto": "usado_buen_estado",
                "modalidad": "venta", "precio": "1000", "carrera_id": "",
            })
            tipo, oid = acuerdos.proponer(pid, 2, {"precio_acordado": "1000"})
            finalizar(tipo, oid)
            reputacion.valorar(tipo, oid, 2, {"valor": "5", "comentario": f"Experiencia número {numero}"})
    pagina = client.get("/estudiantes/3")
    assert pagina.status_code == 200
    assert "Experiencia número 0" not in pagina.text
    assert "Experiencia número 1" in pagina.text
    assert "Experiencia número 2" in pagina.text
    assert "Ver todos los comentarios" in pagina.text
    assert 'href="/estudiantes/3/opiniones"' in pagina.text
    assert "Estudiante de Da Vinci" not in pagina.text
    historial = client.get("/estudiantes/3/opiniones")
    assert historial.status_code == 200
    assert all(f"Experiencia número {n}" in historial.text for n in range(3))
    assert historial.text.index("Experiencia número 2") < historial.text.index("Experiencia número 0")
    assert client.get("/estudiantes/999999/opiniones").status_code == 404


def test_enlace_a_producto_finalizado_respeta_moderacion(app, client, operacion):
    tipo, oid = operacion
    with app.app_context():
        finalizar(tipo, oid)
        reputacion.valorar(tipo, oid, 2, {"valor": "5"})
        opinion = db.query_one("SELECT id FROM valoraciones_operaciones")
        op = (reputacion.prestamos.obtener(oid) if tipo == "prestamo"
              else acuerdos.obtener(tipo, oid))
    ruta = f"/objetos/opiniones/{opinion['id']}/publicacion"
    assert client.get(ruta).status_code == 302
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = 4
    perfil = client.get("/estudiantes/3")
    assert f'href="{ruta}"' in perfil.text
    producto = client.get(ruta)
    assert producto.status_code == 200
    assert "Material de estudio" in producto.text
    assert "Pedir prestado" not in producto.text
    assert "Proponer compra" not in producto.text
    assert "Proponer intercambio" not in producto.text
    with app.app_context():
        db.execute("UPDATE publicaciones SET oculto = 1 WHERE id = :id", id=op["publicacion_id"])
    assert client.get(ruta).status_code == 404


def opiniones_recibidas(receptor, valores, autor=2):
    for numero, valor in enumerate(valores):
        pid = datos.crear(receptor, {
            "titulo": f"Objeto {receptor}-{numero}", "descripcion": "En buen estado",
            "categoria": "dibujo_diseno", "estado_objeto": "usado_buen_estado",
            "modalidad": "venta", "precio": "1000", "carrera_id": "",
        })
        tipo, oid = acuerdos.proponer(pid, autor, {"precio_acordado": "1000"})
        acuerdos.cambiar(tipo, oid, receptor, "aceptar")
        acuerdos.cambiar(tipo, oid, autor, "confirmar")
        acuerdos.cambiar(tipo, oid, receptor, "confirmar")
        reputacion.valorar(tipo, oid, autor, {"valor": str(valor), "comentario": f"Opinión {numero}"})


def entrar(client, usuario_id=4):
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = usuario_id


def test_avisa_al_valorado_con_enlace_a_la_operacion(app, operacion):
    tipo, oid = operacion
    with app.app_context():
        finalizar(tipo, oid)
        db.execute("DELETE FROM notificaciones")
        reputacion.valorar(tipo, oid, 2, {"valor": "5"})
        avisos = db.query("SELECT * FROM notificaciones")
    ruta = f"/objetos/prestamos/{oid}" if tipo == "prestamo" else f"/objetos/acuerdos/{tipo}/{oid}"
    assert [(a["usuario_id"], a["enlace"]) for a in avisos] == [(3, ruta)]
    assert "valoración" in avisos[0]["cuerpo"]


def test_formulario_solo_en_operacion_finalizada_y_nombra_a_la_otra_parte(app, client, operacion):
    tipo, oid = operacion
    ruta = f"/objetos/prestamos/{oid}" if tipo == "prestamo" else f"/objetos/acuerdos/{tipo}/{oid}"
    entrar(client, 3)
    assert "Enviar valoración" not in client.get(ruta).text
    with app.app_context():
        finalizar(tipo, oid)
        nombre = db.query_one("SELECT nombre FROM usuarios WHERE id = 2")["nombre"]
    pagina = client.get(ruta).text
    assert "Enviar valoración" in pagina
    assert f"Valorá a {nombre}" in pagina


def test_operacion_cancelada_no_se_valora_ni_ofrece_formulario(app, client):
    with app.app_context():
        pid = datos.crear(3, {
            "titulo": "Objeto cancelado", "descripcion": "En buen estado",
            "categoria": "dibujo_diseno", "estado_objeto": "usado_buen_estado",
            "modalidad": "venta", "precio": "1000", "carrera_id": "",
        })
        tipo, oid = acuerdos.proponer(pid, 2, {"precio_acordado": "1000"})
        acuerdos.cambiar(tipo, oid, 2, "cancelar")
        with pytest.raises(ValueError):
            reputacion.valorar(tipo, oid, 2, {"valor": "5"})
    entrar(client, 2)
    assert "Enviar valoración" not in client.get(f"/objetos/acuerdos/{tipo}/{oid}").text


@pytest.mark.parametrize(("cantidad", "promedio", "esperada"), [
    (0, None, None), (2, 5, None), (3, 3.4, None), (3, 3.5, "bronce"), (5, 5, "bronce"),
    (6, 3.9, "bronce"), (6, 4, "plata"), (9, 5, "plata"), (10, 4.4, "plata"), (10, 4.5, "oro"),
    (40, 2, None),
])
def test_umbrales_de_insignia(cantidad, promedio, esperada):
    obtenida = reputacion.insignia(cantidad, promedio)
    assert (obtenida["clave"] if obtenida else None) == esperada


def test_promedio_con_cantidad_y_decimal_en_perfil(app, client):
    with app.app_context():
        opiniones_recibidas(3, [5, 4, 4, 5])
    pagina = client.get("/estudiantes/3").text
    assert "4,5" in pagina
    assert "4 opiniones" in pagina
    assert "img/insignias/bronce.png" in pagina


def test_insignia_en_perfil_foro_y_objetos(app, client):
    with app.app_context():
        opiniones_recibidas(3, [5] * 10)
        materia = db.query_one("SELECT id FROM materias ORDER BY id")["id"]
        pregunta = db.query_one(
            "INSERT INTO preguntas (autor_id, materia_id, titulo, cuerpo, creado)"
            " VALUES (3, :materia, 'Consulta', 'Cuerpo', '2026-01-01') RETURNING id", materia=materia,
        )["id"]
        pid = datos.crear(3, {
            "titulo": "Objeto del catálogo", "descripcion": "En buen estado",
            "categoria": "dibujo_diseno", "estado_objeto": "usado_buen_estado",
            "modalidad": "venta", "precio": "1000", "carrera_id": "",
        })
    entrar(client)
    insignia = "img/insignias/oro.png"
    assert insignia in client.get("/estudiantes/3").text
    assert insignia in client.get(f"/foro/preguntas/{pregunta}").text
    assert insignia in client.get("/objetos/").text
    detalle = client.get(f"/objetos/{pid}").text
    assert insignia in detalle
    assert "10 opiniones" in detalle
    assert insignia in client.get("/").text


def test_sin_insignia_con_pocas_opiniones(app, client):
    with app.app_context():
        opiniones_recibidas(3, [5, 5])
    pagina = client.get("/estudiantes/3").text
    assert "img/insignias/bronce.png" not in pagina
    assert "2 opiniones" in pagina


def test_listado_pagina_mas_de_veinte_opiniones(app, client):
    with app.app_context():
        opiniones_recibidas(3, [5] * 21)
    primera = client.get("/estudiantes/3/opiniones")
    assert primera.status_code == 200
    assert "Opinión 0<" not in primera.text
    segunda = client.get("/estudiantes/3/opiniones?pagina=2")
    assert segunda.status_code == 200
    assert "Opinión 0<" in segunda.text


def test_opinion_no_enlaza_a_contenido_moderado(app, client):
    with app.app_context():
        opiniones_recibidas(3, [5])
        opinion = db.query_one("SELECT id FROM valoraciones_operaciones")["id"]
        db.execute("UPDATE publicaciones SET oculto = 1")
    assert f"/objetos/opiniones/{opinion}/publicacion" not in client.get("/estudiantes/3").text


def test_opinion_de_autor_bloqueado_no_enlaza_a_su_perfil(app, client):
    with app.app_context():
        opiniones_recibidas(3, [5])
        db.execute("UPDATE usuarios SET bloqueado = 1 WHERE id = 2")
    pagina = client.get("/estudiantes/3").text
    assert "Opinión 0" in pagina
    assert 'href="/estudiantes/2"' not in pagina


def test_seed_reputacion_da_las_tres_insignias_y_es_repetible(app):
    with app.app_context():
        db.init_db(demo=True)
        assert reputacion_demo.cargar() > 0
        total = db.query_one("SELECT COUNT(*) AS n FROM valoraciones_operaciones")["n"]
        assert reputacion_demo.cargar() == 0
        assert db.query_one("SELECT COUNT(*) AS n FROM valoraciones_operaciones")["n"] == total
        filas = db.query(
            "SELECT u.email, AVG(v.valor) AS promedio, COUNT(*) AS cantidad FROM valoraciones_operaciones v"
            " JOIN usuarios u ON u.id = v.receptor_id GROUP BY u.email",
        )
    claves = {f["email"].split("@")[0]: reputacion.insignia(f["cantidad"], f["promedio"])["clave"] for f in filas}
    assert claves == {"mica": "oro", "tomas": "plata", "lucia": "bronce"}
