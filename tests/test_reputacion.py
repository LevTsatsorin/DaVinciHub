import pytest

from davincihub import db, reputacion
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
    assert "1 opinión" not in pagina.text
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
