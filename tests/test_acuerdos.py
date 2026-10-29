import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from davincihub import db
from davincihub.app import create_app
from davincihub.objetos import acuerdos, datos

PUBLICACION = {"titulo": "Tableta gráfica para diseño", "descripcion": "Incluye lápiz y cable.",
               "categoria": "dibujo_diseno", "estado_objeto": "usado_buen_estado",
               "modalidad": "intercambio", "precio": "30000", "carrera_id": ""}
FORM = {"oferta": "Ofrezco un libro de ilustración en buen estado.", "precio_acordado": "25000"}


@pytest.fixture(autouse=True)
def escenario(app):
    with app.app_context():
        for tabla in ("acuerdos_movimientos", "intercambios", "ventas", "prestamos_movimientos", "prestamos",
                      "coincidencias", "solicitudes", "publicaciones", "notificaciones"):
            db.execute(f"DELETE FROM {tabla}")


def publicar(autor=3, tipo="intercambio", **campos):
    return datos.crear(autor, PUBLICACION | {"modalidad": tipo} | campos)


def proponer(tipo="intercambio", usuario=2, **campos):
    return acuerdos.proponer(publicar(tipo=tipo), usuario, FORM | campos)


def login(client, usuario=2):
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = usuario
    return client


@pytest.mark.parametrize("tipo", ["intercambio", "venta"])
def test_ciclo_completo_exige_confirmacion_de_ambas_partes(app, client, tipo):
    with app.app_context():
        tipo, aid = proponer(tipo)
        a = acuerdos.obtener(tipo, aid)
        assert a["estado"] == "propuesto"
        assert db.query_one("SELECT usuario_id FROM notificaciones")["usuario_id"] == 3
        acuerdos.cambiar(tipo, aid, 3, "aceptar")
        acuerdos.cambiar(tipo, aid, 2, "confirmar")
        a = acuerdos.obtener(tipo, aid)
        assert a["estado"] == "aceptado" and a["confirmado_solicitante"]
        assert datos.obtener(a["publicacion_id"])["estado"] == "activa"
        with pytest.raises(acuerdos.ErrorAcuerdo):
            acuerdos.cambiar(tipo, aid, 2, "confirmar")
        acuerdos.cambiar(tipo, aid, 3, "confirmar")
        a = acuerdos.obtener(tipo, aid)
        assert a["estado"] == "completado" and a["completado"]
        assert datos.obtener(a["publicacion_id"])["estado"] == "cerrada"
        assert [m["estado_nuevo"] for m in acuerdos.movimientos(tipo, aid)] == ["propuesto", "aceptado", "aceptado", "completado"]
        assert len(db.query("SELECT * FROM notificaciones WHERE cuerpo LIKE '%se completó%'") ) == 2
        if tipo == "venta":
            assert a["precio_acordado"] == 25000
    login(client)
    detalle = client.get(f"/objetos/acuerdos/{tipo}/{aid}")
    assert detalle.status_code == 200 and "Completado" in detalle.text
    assert "Ambas personas confirmaron" in detalle.text
    assert PUBLICACION["titulo"] in client.get("/objetos/acuerdos?estado=completado").text


def test_intercambio_con_objeto_propio_reserva_y_cierra_ambos(app):
    with app.app_context():
        p = publicar()
        ofrecida = publicar(2, titulo="Libro de ilustración")
        tipo, aid = acuerdos.proponer(p, 2, FORM | {"publicacion_ofrecida_id": str(ofrecida)})
        acuerdos.cambiar(tipo, aid, 3, "aceptar")
        assert acuerdos.reservada(p) and acuerdos.reservada(ofrecida)
        with pytest.raises(datos.ErrorPublicacion):
            datos.editar(ofrecida, 2, PUBLICACION | {"modalidad": "venta"})
        with pytest.raises(datos.ErrorPublicacion):
            datos.cambiar_estado(ofrecida, 2, "cerrada")
        acuerdos.cambiar(tipo, aid, 3, "confirmar")
        acuerdos.cambiar(tipo, aid, 2, "confirmar")
        assert datos.obtener(p)["estado"] == datos.obtener(ofrecida)["estado"] == "cerrada"
        with pytest.raises(datos.ErrorPublicacion):
            datos.cambiar_estado(ofrecida, 2, "activa")


@pytest.mark.parametrize("tipo", ["intercambio", "venta"])
def test_aceptar_rechaza_otras_pendientes_y_no_permite_segunda_operacion(app, tipo):
    with app.app_context():
        p = publicar(tipo=tipo)
        t, primera = acuerdos.proponer(p, 2, FORM)
        _, segunda = acuerdos.proponer(p, 4, FORM)
        acuerdos.cambiar(t, primera, 3, "aceptar")
        assert acuerdos.obtener(t, segunda)["estado"] == "cancelado"
        assert "automáticamente" in acuerdos.obtener(t, segunda)["motivo_cierre"]
        with pytest.raises(acuerdos.ErrorAcuerdo):
            acuerdos.cambiar(t, segunda, 3, "aceptar")
        with pytest.raises(acuerdos.ErrorAcuerdo):
            acuerdos.proponer(p, 6, FORM)
        acuerdos.cambiar(t, primera, 2, "confirmar")
        acuerdos.cambiar(t, primera, 3, "confirmar")
        with pytest.raises(acuerdos.ErrorAcuerdo):
            acuerdos.proponer(p, 6, FORM)


def test_objeto_ofrecido_no_puede_usarse_en_dos_acuerdos(app):
    with app.app_context():
        p1, p2 = publicar(), publicar(4, titulo="Otra tableta")
        ofrecida = publicar(2, titulo="Mis marcadores")
        t, a1 = acuerdos.proponer(p1, 2, FORM | {"publicacion_ofrecida_id": str(ofrecida)})
        _, a2 = acuerdos.proponer(p2, 2, FORM | {"publicacion_ofrecida_id": str(ofrecida)})
        _, a3 = acuerdos.proponer(ofrecida, 6, FORM)
        acuerdos.cambiar(t, a1, 3, "aceptar")
        assert acuerdos.obtener(t, a2)["estado"] == "cancelado"
        assert acuerdos.obtener(t, a3)["estado"] == "cancelado"


@pytest.mark.parametrize("cambio", ["ajeno", "prestamo", "venta", "pausada", "cerrada", "oculta", "ocupada", "inexistente"])
def test_valida_publicacion_ofrecida(app, cambio):
    with app.app_context():
        p = publicar()
        ofrecida = publicar(2, titulo="Objeto ofrecido")
        if cambio == "ajeno":
            ofrecida = publicar(4)
        elif cambio in ("prestamo", "venta"):
            datos.editar(ofrecida, 2, PUBLICACION | {"modalidad": cambio})
        elif cambio in ("pausada", "cerrada"):
            datos.cambiar_estado(ofrecida, 2, cambio)
        elif cambio == "oculta":
            db.execute("UPDATE publicaciones SET oculto = 1 WHERE id = :id", id=ofrecida)
        elif cambio == "ocupada":
            t, aid = acuerdos.proponer(ofrecida, 6, FORM)
            acuerdos.cambiar(t, aid, 2, "aceptar")
        else:
            ofrecida = 999999
        with pytest.raises(acuerdos.ErrorAcuerdo):
            acuerdos.proponer(p, 2, FORM | {"publicacion_ofrecida_id": str(ofrecida)})


@pytest.mark.parametrize("precio", ["", "0", "-1", "NaN", "Infinity", "1.001", "1000000000", "texto"])
def test_venta_valida_precio_sin_crear_acuerdo(app, precio):
    with app.app_context():
        p = publicar(tipo="venta")
        with pytest.raises(acuerdos.ErrorAcuerdo) as error:
            acuerdos.proponer(p, 2, FORM | {"precio_acordado": precio})
        assert "precio_acordado" in error.value.errores
        assert db.query_one("SELECT count(*) AS n FROM ventas")["n"] == 0


@pytest.mark.parametrize("campo,valor", [("oferta", ""), ("oferta", "x" * 2001),
                                         ("publicacion_ofrecida_id", "²"), ("publicacion_ofrecida_id", "-2"),
                                         ("publicacion_ofrecida_id", "9" * 40)])
def test_valida_oferta_y_id(app, campo, valor):
    with app.app_context(), pytest.raises(acuerdos.ErrorAcuerdo):
        proponer(**{campo: valor})


@pytest.mark.parametrize("tipo", ["intercambio", "venta"])
@pytest.mark.parametrize("actor,accion,aceptado", [(3, "rechazar", False), (2, "cancelar", False),
                                                   (3, "cancelar", True), (2, "cancelar", True)])
def test_rechazo_y_cancelacion_conservan_historial_y_liberan(app, tipo, actor, accion, aceptado):
    with app.app_context():
        t, aid = proponer(tipo)
        p = acuerdos.obtener(t, aid)["publicacion_id"]
        if aceptado:
            acuerdos.cambiar(t, aid, 3, "aceptar")
        acuerdos.cambiar(t, aid, actor, accion)
        a = acuerdos.obtener(t, aid)
        assert a["estado"] == "cancelado" and a["motivo_cierre"]
        assert not acuerdos.reservada(p)
        assert datos.obtener(p)["estado"] == "activa"
        assert acuerdos.listar(2, estado="cancelado")["total"] == 1
        assert acuerdos.listar(3, vista="recibidas")["total"] == 1
        assert acuerdos.movimientos(t, aid)[-1]["estado_nuevo"] == "cancelado"


@pytest.mark.parametrize("estado,actor,accion", [
    ("propuesto", 2, "aceptar"), ("propuesto", 2, "rechazar"), ("propuesto", 3, "confirmar"),
    ("aceptado", 3, "aceptar"), ("aceptado", 3, "rechazar"),
    ("cancelado", 3, "aceptar"), ("cancelado", 2, "confirmar"),
    ("completado", 3, "aceptar"), ("completado", 3, "confirmar"), ("completado", 2, "cancelar"),
    ("propuesto", 3, "inventado"),
])
def test_transiciones_invalidas_no_modifican_estado(app, estado, actor, accion):
    with app.app_context():
        t, aid = proponer()
        if estado in ("aceptado", "completado"):
            acuerdos.cambiar(t, aid, 3, "aceptar")
        if estado == "completado":
            acuerdos.cambiar(t, aid, 3, "confirmar")
            acuerdos.cambiar(t, aid, 2, "confirmar")
        if estado == "cancelado":
            acuerdos.cambiar(t, aid, 2, "cancelar")
        previo = acuerdos.obtener(t, aid)
        with pytest.raises(acuerdos.ErrorAcuerdo):
            acuerdos.cambiar(t, aid, actor, accion)
        assert acuerdos.obtener(t, aid) == previo


def test_no_propias_ni_duplicadas_y_solo_participantes(app, client):
    with app.app_context():
        p = publicar()
        with pytest.raises(acuerdos.ErrorAcuerdo):
            acuerdos.proponer(p, 3, FORM)
        t, aid = acuerdos.proponer(p, 2, FORM)
        with pytest.raises(acuerdos.ErrorAcuerdo):
            acuerdos.proponer(p, 2, FORM)
        with pytest.raises(PermissionError):
            acuerdos.cambiar(t, aid, 4, "aceptar")
    url = f"/objetos/acuerdos/{t}/{aid}"
    assert client.get(url).status_code == 302
    login(client, 4)
    assert client.get(url).status_code == 404
    assert client.post(url + "/accion", data={"accion": "aceptar"}).status_code == 404
    assert PUBLICACION["titulo"] not in client.get("/objetos/acuerdos").text
    assert client.get("/objetos/acuerdos/inventado/1").status_code == 404
    login(client, 1)
    assert client.get("/objetos/acuerdos").status_code == 403
    assert client.post(f"/objetos/{p}/proponer", data=FORM).status_code == 403
    login(client, 5)
    assert client.get(url).status_code == 403


@pytest.mark.parametrize("cambio", ["oculto", "pausada", "cerrada", "bloqueado", "modalidad"])
def test_revalida_publicacion_y_solicitante_al_aceptar(app, cambio):
    with app.app_context():
        t, aid = proponer()
        p = acuerdos.obtener(t, aid)["publicacion_id"]
        if cambio == "oculto":
            db.execute("UPDATE publicaciones SET oculto = 1 WHERE id = :id", id=p)
        elif cambio in ("pausada", "cerrada"):
            datos.cambiar_estado(p, 3, cambio)
        elif cambio == "bloqueado":
            db.execute("UPDATE usuarios SET bloqueado = 1 WHERE id = 2")
        else:
            datos.editar(p, 3, PUBLICACION | {"modalidad": "prestamo"})
        with pytest.raises(acuerdos.ErrorAcuerdo):
            acuerdos.cambiar(t, aid, 3, "aceptar")
        assert acuerdos.obtener(t, aid)["estado"] == "propuesto"


def test_venta_conserva_precio_propuesto_y_no_toma_objeto_adjuntado(app):
    with app.app_context():
        p = publicar(tipo="venta")
        t, aid = acuerdos.proponer(p, 2, FORM | {"publicacion_ofrecida_id": "999999"})
        datos.editar(p, 3, PUBLICACION | {"modalidad": "venta", "precio": "99000"})
        acuerdos.cambiar(t, aid, 3, "aceptar")
        assert acuerdos.obtener(t, aid)["precio_acordado"] == 25000
        assert acuerdos.obtener(t, aid)["publicacion_ofrecida_id"] is None


@pytest.mark.parametrize("tipo", ["intercambio", "venta"])
def test_aceptaciones_simultaneas_solo_aceptan_una(app, tipo):
    with app.app_context():
        p = publicar(tipo=tipo)
        t, a1 = acuerdos.proponer(p, 2, FORM)
        _, a2 = acuerdos.proponer(p, 4, FORM)
    barrera = Barrier(2)

    def aceptar(aid):
        with app.app_context():
            barrera.wait(timeout=5)
            try:
                acuerdos.cambiar(t, aid, 3, "aceptar")
                return "aceptado"
            except acuerdos.ErrorAcuerdo:
                return "rechazado"
    with ThreadPoolExecutor(max_workers=2) as equipo:
        assert sorted(equipo.map(aceptar, (a1, a2))) == ["aceptado", "rechazado"]
    with app.app_context():
        assert sorted(acuerdos.obtener(t, aid)["estado"] for aid in (a1, a2)) == ["aceptado", "cancelado"]


@pytest.mark.parametrize("accion", ["proponer", "aceptar", "rechazar", "cancelar", "confirmar", "completar"])
def test_error_de_aviso_revierte_estado_cierre_y_otras_propuestas(app, monkeypatch, accion):
    def falla(*args, **kwargs):
        raise RuntimeError("Aviso no disponible")
    with app.app_context():
        p = publicar()
        ofrecida = publicar(2, titulo="Libro ofrecido")
        t, aid = acuerdos.proponer(p, 2, FORM | {"publicacion_ofrecida_id": str(ofrecida)})
        _, otra = acuerdos.proponer(p, 4, FORM)
        if accion in ("confirmar", "completar"):
            acuerdos.cambiar(t, aid, 3, "aceptar")
        if accion == "completar":
            acuerdos.cambiar(t, aid, 3, "confirmar")
        previo = acuerdos.obtener(t, aid)
        previo_otra = acuerdos.obtener(t, otra)
        monkeypatch.setattr(acuerdos, "notificar", falla)
        with pytest.raises(RuntimeError):
            if accion == "proponer":
                acuerdos.proponer(p, 6, FORM)
            else:
                acuerdos.cambiar(t, aid, 2 if accion in ("completar", "cancelar") else 3, "confirmar" if accion == "completar" else accion)
        assert acuerdos.obtener(t, aid) == previo
        assert acuerdos.obtener(t, otra) == previo_otra
        assert datos.obtener(p)["estado"] == datos.obtener(ofrecida)["estado"] == "activa"
        assert len(db.query("SELECT id FROM intercambios")) == 2


@pytest.mark.parametrize("tipo", ["intercambio", "venta"])
def test_formularios_detalle_listado_y_csrf(app, client, tipo):
    with app.app_context():
        p = publicar(tipo=tipo)
    login(client)
    url = f"/objetos/{p}/proponer"
    assert client.get(url).status_code == 200
    assert ("Proponer compra" if tipo == "venta" else "Proponer intercambio") in client.get(f"/objetos/{p}").text
    invalidos = FORM | ({"precio_acordado": ""} if tipo == "venta" else {"oferta": ""})
    assert client.post(url, data=invalidos).status_code == 400
    respuesta = client.post(url, data=FORM)
    assert respuesta.status_code == 302
    assert client.get(respuesta.location).status_code == 200
    assert client.get(url).location == respuesta.location
    assert "Ver mi propuesta" in client.get(f"/objetos/{p}").text
    assert PUBLICACION["titulo"] in client.get(f"/objetos/acuerdos?tipo={tipo}&estado=propuesto").text
    assert PUBLICACION["titulo"] not in client.get("/objetos/acuerdos?estado=completado").text
    login(client, 3)
    assert PUBLICACION["titulo"] in client.get("/objetos/acuerdos?vista=recibidas").text
    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post(respuesta.location + "/accion", data={"accion": "aceptar"}).status_code == 400
    assert client.post(url, data=FORM).status_code == 400


def test_paginacion_combinada_y_parametros_invalidos(app, client):
    with app.app_context():
        for n in range(14):
            proponer("venta" if n % 2 else "intercambio")
    login(client)
    respuesta = client.get("/objetos/acuerdos?vista=enviadas&estado=propuesto&pagina=2")
    assert respuesta.status_code == 200
    assert "Página 2 de 2" in respuesta.text and "estado=propuesto" in respuesta.text
    assert client.get("/objetos/acuerdos?vista=otro&tipo=otro&estado=otro&pagina=abc").status_code == 200


def test_migracion_aditiva_preserva_precios_y_ofertas(tmp_path):
    ruta = tmp_path / "anterior.db"
    with sqlite3.connect(ruta) as con:
        con.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY)")
        con.execute("CREATE TABLE ventas (id INTEGER PRIMARY KEY, precio_acordado REAL, estado TEXT)")
        con.execute("INSERT INTO ventas VALUES (1, 12000, 'aceptada')")
        con.execute("CREATE TABLE intercambios (id INTEGER PRIMARY KEY, oferta TEXT, estado TEXT)")
        con.execute("INSERT INTO intercambios VALUES (1, 'Libro de diseño', 'propuesto')")
    for _ in range(2):
        create_app({"DATABASE_URL": f"sqlite:///{ruta}"})
    with sqlite3.connect(ruta) as con:
        assert con.execute("SELECT precio_acordado, estado, confirmado_propietario FROM ventas").fetchone() == (12000, 'aceptada', 0)
        assert con.execute("SELECT oferta, estado, motivo_cierre FROM intercambios").fetchone() == ('Libro de diseño', 'propuesto', '')
        assert con.execute("SELECT name FROM sqlite_master WHERE name = 'acuerdos_movimientos'").fetchone()


def test_demo_aditivo_conserva_c2_c3_y_no_duplica_acuerdos(app):
    from davincihub.objetos import acuerdos_demo, busquedas, prestamos
    with app.app_context():
        p = publicar(tipo="prestamo")
        sid = prestamos.solicitar(p, 2, {"fecha_entrega": prestamos.hoy_local(), "fecha_devolucion": prestamos.hoy_local()})
        bid, _ = busquedas.crear(2, {"titulo": "Tableta", "categoria": "dibujo_diseno"})
        assert acuerdos_demo.cargar() == 6
        assert acuerdos_demo.cargar() == 0
        assert prestamos.obtener(sid)["estado"] == "pendiente"
        assert busquedas.obtener(bid)["estado"] == "activa"
        filas = acuerdos.listar(2)["acuerdos"] + acuerdos.listar(2, vista="recibidas")["acuerdos"]
        assert {a["estado"] for a in filas} == set(acuerdos.ESTADOS)
        assert any(a["confirmado_solicitante"] and a["estado"] == "aceptado" for a in filas)


def test_aceptaciones_simultaneas_con_ofrecida_compartida(app):
    with app.app_context():
        p1, p2, ofrecida = publicar(), publicar(4), publicar(2)
        t, a1 = acuerdos.proponer(p1, 2, FORM | {"publicacion_ofrecida_id": str(ofrecida)})
        _, a2 = acuerdos.proponer(p2, 2, FORM | {"publicacion_ofrecida_id": str(ofrecida)})
    barrera = Barrier(2)
    def aceptar(par):
        with app.app_context():
            barrera.wait(timeout=5)
            try:
                acuerdos.cambiar(t, par[0], par[1], "aceptar")
                return True
            except acuerdos.ErrorAcuerdo:
                return False
    with ThreadPoolExecutor(max_workers=2) as equipo:
        assert sorted(equipo.map(aceptar, ((a1, 3), (a2, 4)))) == [False, True]


def test_confirmaciones_simultaneas_completan_una_sola_vez(app):
    with app.app_context():
        t, aid = proponer("venta")
        acuerdos.cambiar(t, aid, 3, "aceptar")
    barrera = Barrier(2)
    def confirmar(usuario):
        with app.app_context():
            barrera.wait(timeout=5)
            acuerdos.cambiar(t, aid, usuario, "confirmar")
    with ThreadPoolExecutor(max_workers=2) as equipo:
        list(equipo.map(confirmar, (2, 3)))
    with app.app_context():
        assert acuerdos.obtener(t, aid)["estado"] == "completado"
        assert len(db.query("SELECT * FROM acuerdos_movimientos WHERE estado_nuevo = 'completado'")) == 1
        assert len(db.query("SELECT * FROM notificaciones WHERE cuerpo LIKE '%se completó%'")) == 2
