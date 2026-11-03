import pytest

from davincihub import db, reputacion
from davincihub.objetos import acuerdos, datos, historial


def publicar(autor, titulo, modalidad="venta"):
    return datos.crear(autor, {
        "titulo": titulo, "descripcion": "En buen estado", "categoria": "dibujo_diseno",
        "estado_objeto": "usado_buen_estado", "modalidad": modalidad, "precio": "1000", "carrera_id": "",
    })


def prestamo(publicacion, solicitante, estado="pendiente"):
    return db.query_one(
        "INSERT INTO prestamos (publicacion_id, solicitante_id, estado, fecha_entrega, fecha_devolucion, creado)"
        " VALUES (:p, :s, :e, '2026-01-01', '2026-01-05', '2026-01-01T10:00:00+00:00') RETURNING id",
        p=publicacion, s=solicitante, e=estado,
    )["id"]


def acuerdo(publicacion, solicitante, estado="propuesto"):
    tipo, oid = acuerdos.proponer(publicacion, solicitante, {"oferta": "Un libro", "precio_acordado": "900"})
    if estado == "completado":
        acuerdos.cambiar(tipo, oid, 3, "aceptar")
        acuerdos.cambiar(tipo, oid, solicitante, "confirmar")
        acuerdos.cambiar(tipo, oid, 3, "confirmar")
    elif estado == "cancelado":
        acuerdos.cambiar(tipo, oid, solicitante, "cancelar")
    return tipo, oid


def entrar(client, usuario_id):
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = usuario_id


def claves(resultado):
    return {(o["tipo"], o["id"]) for o in resultado["operaciones"]}


def test_reune_publicaciones_prestamos_intercambios_y_ventas(app):
    with app.app_context():
        mia = publicar(3, "Mi publicación")
        pr = prestamo(publicar(3, "Para prestar", "prestamo"), 2)
        pedido = prestamo(publicar(2, "Ajeno", "prestamo"), 3)
        inter = acuerdo(publicar(3, "Para cambiar", "intercambio"), 2)
        venta = acuerdo(publicar(3, "Para vender"), 2, "completado")
        vista = claves(historial.listar(3))
    assert ("publicacion", mia) in vista
    assert {("prestamo", pr), ("prestamo", pedido), inter, venta} <= vista


def test_cada_usuario_ve_solo_lo_suyo(app, client):
    with app.app_context():
        publicar(3, "Secreto de tres")
        prestamo(publicar(3, "Préstamo de tres", "prestamo"), 2)
        acuerdo(publicar(3, "Venta de tres"), 2)
    entrar(client, 4)
    pagina = client.get("/objetos/historial?usuario_id=3&autor_id=3").text
    for titulo in ("Secreto de tres", "Préstamo de tres", "Venta de tres"):
        assert titulo not in pagina
    entrar(client, 2)
    pagina = client.get("/objetos/historial").text
    assert "Secreto de tres" not in pagina
    assert "Préstamo de tres" in pagina
    assert "Venta de tres" in pagina


def test_exige_login_y_rechaza_admin(app, client):
    assert client.get("/objetos/historial").status_code == 302
    with app.app_context():
        admin = db.query_one(
            "INSERT INTO usuarios (nombre, apellido, email, password_hash, rol, creado)"
            " VALUES ('A', 'D', 'adm@davinci.edu.ar', 'x', 'admin', '2026-01-01') RETURNING id"
        )["id"]
    entrar(client, admin)
    assert client.get("/objetos/historial").status_code == 403


def test_canceladas_se_muestran(app, client):
    with app.app_context():
        _, oid = acuerdo(publicar(3, "Venta cancelada"), 2, "cancelado")
        assert ("venta", oid) in claves(historial.listar(2, estado="cancelado"))
    entrar(client, 2)
    pagina = client.get("/objetos/historial").text
    assert "Venta cancelada" in pagina
    assert "Cancelado" in pagina


def test_filtra_por_tipo_y_estado(app):
    with app.app_context():
        publicar(3, "Publicación")
        p_pendiente = prestamo(publicar(3, "Uno", "prestamo"), 2)
        p_devuelto = prestamo(publicar(3, "Dos", "prestamo"), 2, "devuelto")
        _, venta = acuerdo(publicar(3, "Tres"), 2, "completado")
        _, inter = acuerdo(publicar(3, "Cuatro", "intercambio"), 2)
        assert claves(historial.listar(2, tipo="prestamo")) == {("prestamo", p_pendiente), ("prestamo", p_devuelto)}
        assert claves(historial.listar(2, tipo="prestamo", estado="devuelto")) == {("prestamo", p_devuelto)}
        assert claves(historial.listar(2, estado="completado")) == {("venta", venta)}
        assert claves(historial.listar(2, tipo="venta", estado="completado")) == {("venta", venta)}
        assert claves(historial.listar(2, tipo="intercambio")) == {("intercambio", inter)}
        assert {o["tipo"] for o in historial.listar(3, tipo="publicacion")["operaciones"]} == {"publicacion"}


def test_filtros_invalidos_se_ignoran_y_estado_ajeno_al_tipo_se_descarta(app, client):
    with app.app_context():
        pid = publicar(3, "Publicación")
        resultado = historial.listar(3, tipo="inventado", estado="inventado")
        assert ("publicacion", pid) in claves(resultado)
        assert resultado["tipo"] == "" and resultado["estado"] == ""
        assert historial.listar(3, tipo="publicacion", estado="devuelto")["estado"] == ""
    entrar(client, 3)
    assert client.get("/objetos/historial?tipo=x&estado=y&pagina=abc").status_code == 200


def test_muestra_estado_fechas_y_otra_parte(app, client):
    with app.app_context():
        nombre = db.query_one("SELECT nombre FROM usuarios WHERE id = 2")["nombre"]
        prestamo(publicar(3, "Con fechas", "prestamo"), 2, "devuelto")
    entrar(client, 3)
    pagina = client.get("/objetos/historial").text
    assert "01/01/2026" in pagina and "05/01/2026" in pagina
    assert "Devuelto" in pagina
    assert nombre in pagina


def test_finalizada_ofrece_valorar_y_luego_muestra_la_valoracion(app, client):
    with app.app_context():
        pr = prestamo(publicar(3, "Finalizado", "prestamo"), 2, "devuelto")
    entrar(client, 2)
    ruta = f"/objetos/prestamos/{pr}#valorar"
    pagina = client.get("/objetos/historial").text
    assert ruta in pagina and "Valorar a" in pagina
    assert 'id="valorar"' in client.get(f"/objetos/prestamos/{pr}").text
    with app.app_context():
        reputacion.valorar("prestamo", pr, 2, {"valor": "4"})
    pagina = client.get("/objetos/historial").text
    assert "Valorar a" not in pagina
    assert "Tu valoración" in pagina and "4 / 5" in pagina


@pytest.mark.parametrize("estado", ["pendiente", "aceptado", "en_prestamo", "vencido", "cancelado"])
def test_no_ofrece_valorar_si_no_esta_finalizada(app, client, estado):
    with app.app_context():
        prestamo(publicar(3, "Sin finalizar", "prestamo"), 2, estado)
    entrar(client, 2)
    assert "Valorar a" not in client.get("/objetos/historial").text


def test_publicacion_oculta_se_ve_marcada_solo_para_su_duenio(app, client):
    with app.app_context():
        pid = publicar(3, "Moderada")
        db.execute("UPDATE publicaciones SET oculto = 1 WHERE id = :id", id=pid)
    entrar(client, 3)
    pagina = client.get("/objetos/historial").text
    assert "Moderada" in pagina and "Oculta por moderación" in pagina


def test_cierre_de_operacion_muestra_fecha_final(app):
    with app.app_context():
        tipo, oid = acuerdo(publicar(3, "Terminada"), 2, "completado")
        fila = next(o for o in historial.listar(2)["operaciones"] if o["id"] == oid and o["tipo"] == tipo)
        assert fila["cierre"]
        tipo, oid = acuerdo(publicar(3, "Anulada"), 2, "cancelado")
        fila = next(o for o in historial.listar(2)["operaciones"] if o["id"] == oid and o["tipo"] == tipo)
        assert fila["cierre"]


def test_pagina_sin_repetir_y_con_enlace(app, client):
    with app.app_context():
        base = historial.listar(3)["total"]
        for numero in range(datos.POR_PAGINA + 1):
            publicar(3, f"Objeto {numero}")
        primera = historial.listar(3, pagina=1)
        segunda = historial.listar(3, pagina=2)
        assert primera["total"] == base + datos.POR_PAGINA + 1
        assert not claves(primera) & claves(segunda)
    entrar(client, 3)
    assert "pagina=2" in client.get("/objetos/historial").text


def test_no_consulta_por_cada_fila(app):
    with app.app_context():
        for numero in range(5):
            prestamo(publicar(3, f"Objeto {numero}", "prestamo"), 2)
        consultas = []
        original = db.query
        db.query = lambda *a, **k: (consultas.append(a[0]), original(*a, **k))[1]
        try:
            historial.listar(3)
        finally:
            db.query = original
        assert len(consultas) == 2


def test_enlace_en_el_menu(app, client):
    entrar(client, 3)
    assert 'href="/objetos/historial"' in client.get("/objetos/").text




def test_tarjeta_usa_el_lenguaje_visual_del_catalogo(app, client):
    with app.app_context():
        prestamo(publicar(3, "Con otra parte", "prestamo"), 2, "devuelto")
    entrar(client, 3)
    pagina = client.get("/objetos/historial").text
    assert "objeto-dibujo_diseno" in pagina
    assert "objeto-modalidad-prestamo" in pagina
    assert "objeto-autor-avatar" in pagina


def test_pestanias_muestran_cantidad_por_tipo(app, client):
    with app.app_context():
        base = historial.cantidades(3)
        prestamo(publicar(3, "Uno", "prestamo"), 2)
        cantidades = historial.cantidades(3)
    assert cantidades["prestamo"] == base.get("prestamo", 0) + 1
    assert cantidades["publicacion"] == base.get("publicacion", 0) + 1
    assert cantidades.get("venta", 0) == 0
