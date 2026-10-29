import sqlite3

import pytest

from davincihub import db
from davincihub.app import create_app
from davincihub.objetos import datos, prestamos

PUBLICACION = {"titulo": "Cámara Canon para cortometrajes", "descripcion": "Con lente y cargador.",
               "categoria": "foto_video", "estado_objeto": "usado_buen_estado",
               "modalidad": "prestamo", "carrera_id": ""}


@pytest.fixture(autouse=True)
def escenario(app, monkeypatch):
    monkeypatch.setattr(prestamos, "hoy_local", lambda: "2026-10-29")
    with app.app_context():
        for tabla in ("prestamos_movimientos", "prestamos", "coincidencias", "solicitudes", "publicaciones", "notificaciones"):
            db.execute(f"DELETE FROM {tabla}")


@pytest.fixture
def publicacion(app):
    with app.app_context():
        return datos.crear(3, PUBLICACION)


@pytest.fixture
def solicitud(app, publicacion):
    with app.app_context():
        return prestamos.solicitar(publicacion, 2, fechas())


def fechas(**cambios):
    return {"fecha_entrega": "2026-10-29", "fecha_devolucion": "2026-11-02",
            "condiciones": "Entregar con lente y cargador en la biblioteca.", **cambios}


def login(client, usuario=2):
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = usuario
    return client


def test_solicitud_y_ciclo_completo_con_fechas_participantes_y_avisos(app, client, solicitud):
    login(client, 3)
    detalle = client.get(f"/objetos/prestamos/{solicitud}")
    assert "Aceptar préstamo" in detalle.text
    assert client.post(f"/objetos/prestamos/{solicitud}/accion", data=fechas(accion="aceptar")).status_code == 302
    with app.app_context():
        prestamos.cambiar(solicitud, 3, "entregar")
        pr = prestamos.obtener(solicitud)
        assert pr["estado"] == "en_prestamo" and pr["entregado"] and not pr["devuelto"]
        assert pr["propietario_id"] == 3 and pr["solicitante_id"] == 2
        assert pr["fecha_entrega"] == "2026-10-29" and pr["fecha_devolucion"] == "2026-11-02"
        prestamos.cambiar(solicitud, 3, "devolver")
        pr = prestamos.obtener(solicitud)
        assert pr["estado"] == "devuelto" and pr["devuelto"]
        assert pr["condiciones"] == fechas()["condiciones"]
        assert [m["estado_nuevo"] for m in prestamos.movimientos(solicitud)] == [
            "pendiente", "aceptado", "en_prestamo", "devuelto"]
        avisos = db.query("SELECT * FROM notificaciones ORDER BY id")
        assert [a["usuario_id"] for a in avisos] == [3, 2, 2, 2]
        assert all(a["enlace"] == f"/objetos/prestamos/{solicitud}" for a in avisos)
    assert "Devuelto" in client.get(f"/objetos/prestamos/{solicitud}").text


@pytest.mark.parametrize("campos,campo", [
    ({"fecha_entrega": ""}, "fecha_entrega"),
    ({"fecha_entrega": "2026-02-30"}, "fecha_entrega"),
    ({"fecha_entrega": "20261029"}, "fecha_entrega"),
    ({"fecha_entrega": "2026-10-28"}, "fecha_entrega"),
    ({"fecha_devolucion": "2026-10-28"}, "fecha_devolucion"),
    ({"fecha_devolucion": ""}, "fecha_devolucion"),
    ({"mensaje": "a" * 2001}, "mensaje"),
])
def test_valida_solicitud_sin_guardar(app, publicacion, campos, campo):
    with app.app_context(), pytest.raises(prestamos.ErrorPrestamo) as error:
        prestamos.solicitar(publicacion, 2, fechas(**campos))
    assert campo in error.value.errores
    with app.app_context():
        assert db.query_one("SELECT count(*) AS n FROM prestamos")["n"] == 0
        assert db.query_one("SELECT count(*) AS n FROM notificaciones")["n"] == 0


def test_fechas_del_mismo_dia_y_cambios_acordados(app, publicacion):
    with app.app_context():
        sid = prestamos.solicitar(publicacion, 2, fechas(fecha_devolucion="2026-10-29"))
        prestamos.cambiar(sid, 3, "aceptar", fechas(fecha_entrega="2026-10-30", fecha_devolucion="2026-10-31"))
        assert prestamos.obtener(sid)["fecha_entrega"] == "2026-10-30"
        with pytest.raises(prestamos.ErrorPrestamo):
            prestamos.cambiar(sid, 3, "entregar")


@pytest.mark.parametrize("campo,valor", [("condiciones", ""), ("condiciones", "a" * 2001),
                                         ("fecha_entrega", "2026-10-28"), ("fecha_devolucion", "2026-10-28")])
def test_aceptar_valida_acuerdo_y_preserva_pendiente(app, solicitud, campo, valor):
    with app.app_context():
        with pytest.raises(prestamos.ErrorPrestamo):
            prestamos.cambiar(solicitud, 3, "aceptar", fechas(**{campo: valor}))
        assert prestamos.obtener(solicitud)["estado"] == "pendiente"
        assert len(prestamos.movimientos(solicitud)) == 1


@pytest.mark.parametrize("estado,accion,actor", [
    ("pendiente", "entregar", 3), ("pendiente", "devolver", 3),
    ("pendiente", "aceptar", 2), ("pendiente", "rechazar", 2),
    ("aceptado", "aceptar", 3), ("aceptado", "entregar", 2), ("aceptado", "devolver", 3),
    ("en_prestamo", "cancelar", 2), ("en_prestamo", "cancelar", 3),
    ("en_prestamo", "devolver", 2), ("en_prestamo", "entregar", 3),
    ("devuelto", "devolver", 3), ("devuelto", "cancelar", 2),
    ("cancelado", "aceptar", 3), ("cancelado", "entregar", 3),
    ("pendiente", "inventado", 3),
])
def test_transiciones_invalidas_no_cambian_datos(app, solicitud, estado, accion, actor):
    with app.app_context():
        if estado in ("aceptado", "en_prestamo", "devuelto"):
            prestamos.cambiar(solicitud, 3, "aceptar", fechas())
        if estado in ("en_prestamo", "devuelto"):
            prestamos.cambiar(solicitud, 3, "entregar")
        if estado == "devuelto":
            prestamos.cambiar(solicitud, 3, "devolver")
        if estado == "cancelado":
            prestamos.cambiar(solicitud, 2, "cancelar")
        avisos = db.query_one("SELECT count(*) AS n FROM notificaciones")["n"]
        with pytest.raises(prestamos.ErrorPrestamo):
            prestamos.cambiar(solicitud, actor, accion, fechas())
        assert prestamos.obtener(solicitud)["estado"] == estado
        assert db.query_one("SELECT count(*) AS n FROM notificaciones")["n"] == avisos


@pytest.mark.parametrize("aceptado,actor,accion", [(False, 3, "rechazar"), (False, 2, "cancelar"),
                                                    (True, 2, "cancelar"), (True, 3, "cancelar")])
def test_cancelacion_y_rechazo_se_conservan(app, solicitud, aceptado, actor, accion):
    with app.app_context():
        if aceptado:
            prestamos.cambiar(solicitud, 3, "aceptar", fechas())
        prestamos.cambiar(solicitud, actor, accion)
        pr = prestamos.obtener(solicitud)
        assert pr["estado"] == "cancelado" and pr["motivo_cierre"]
        assert prestamos.listar(2, estado="cancelado")["total"] == 1
        assert prestamos.listar(3, vista="otorgados", estado="cancelado")["total"] == 1
        assert not prestamos.ocupado(pr["publicacion_id"])


def test_objeto_propio_duplicado_y_doble_aceptacion(app, publicacion, solicitud):
    with app.app_context():
        with pytest.raises(prestamos.ErrorPrestamo):
            prestamos.solicitar(publicacion, 3, fechas())
        with pytest.raises(prestamos.ErrorPrestamo):
            prestamos.solicitar(publicacion, 2, fechas())
        otra = prestamos.solicitar(publicacion, 4, fechas())
        prestamos.cambiar(solicitud, 3, "aceptar", fechas())
        with pytest.raises(prestamos.ErrorPrestamo):
            prestamos.cambiar(otra, 3, "aceptar", fechas())
        with pytest.raises(prestamos.ErrorPrestamo):
            prestamos.solicitar(publicacion, 6, fechas())
        prestamos.cambiar(solicitud, 2, "cancelar")
        prestamos.cambiar(otra, 3, "aceptar", fechas())
        assert prestamos.obtener(otra)["estado"] == "aceptado"


@pytest.mark.parametrize("cambio", ["venta", "intercambio", "pausada", "cerrada", "oculto", "bloqueado"])
def test_publicacion_no_disponible_no_se_puede_solicitar(app, publicacion, cambio):
    with app.app_context():
        if cambio in ("venta", "intercambio"):
            datos.editar(publicacion, 3, PUBLICACION | {"modalidad": cambio, "precio": "10"})
        elif cambio in ("pausada", "cerrada"):
            datos.cambiar_estado(publicacion, 3, cambio)
        elif cambio == "oculto":
            db.execute("UPDATE publicaciones SET oculto = 1 WHERE id = :id", id=publicacion)
        else:
            db.execute("UPDATE usuarios SET bloqueado = 1 WHERE id = 3")
        with pytest.raises(prestamos.ErrorPrestamo):
            prestamos.solicitar(publicacion, 2, fechas())


def test_cambio_de_modalidad_y_cierre_no_rompen_prestamo(app, solicitud, publicacion):
    with app.app_context():
        prestamos.cambiar(solicitud, 3, "aceptar", fechas())
        with pytest.raises(datos.ErrorPublicacion):
            datos.editar(publicacion, 3, PUBLICACION | {"modalidad": "venta", "precio": "100"})
        with pytest.raises(datos.ErrorPublicacion):
            datos.cambiar_estado(publicacion, 3, "cerrada")
        datos.cambiar_estado(publicacion, 3, "pausada")
        prestamos.cambiar(solicitud, 3, "entregar")
        prestamos.cambiar(solicitud, 3, "devolver")
        datos.cambiar_estado(publicacion, 3, "cerrada")


def test_vencimiento_avisa_una_vez_a_ambos_y_permite_devolver(app, client, solicitud, monkeypatch):
    with app.app_context():
        prestamos.cambiar(solicitud, 3, "aceptar", fechas())
        prestamos.cambiar(solicitud, 3, "entregar")
        monkeypatch.setattr(prestamos, "hoy_local", lambda: "2026-11-02")
        assert prestamos.actualizar_vencidos() == 0  # fecha límite inclusive
        monkeypatch.setattr(prestamos, "hoy_local", lambda: "2026-11-03")
    login(client)
    assert client.get("/notificaciones/").status_code == 200  # barrido automático
    with app.app_context():
        assert prestamos.obtener(solicitud)["estado"] == "vencido"
        assert prestamos.actualizar_vencidos() == 0
        avisos = db.query("SELECT usuario_id FROM notificaciones WHERE cuerpo LIKE '%está vencido%'")
        assert sorted(a["usuario_id"] for a in avisos) == [2, 3]
        with pytest.raises(prestamos.ErrorPrestamo):
            prestamos.cambiar(solicitud, 3, "cancelar")
        prestamos.cambiar(solicitud, 3, "devolver")
        assert prestamos.obtener(solicitud)["estado"] == "devuelto"


def test_no_marca_aceptado_sin_entrega_como_vencido(app, solicitud, monkeypatch):
    with app.app_context():
        prestamos.cambiar(solicitud, 3, "aceptar", fechas())
        monkeypatch.setattr(prestamos, "hoy_local", lambda: "2026-11-03")
        assert prestamos.actualizar_vencidos() == 0
        with pytest.raises(prestamos.ErrorPrestamo):
            prestamos.cambiar(solicitud, 3, "entregar")
        prestamos.cambiar(solicitud, 3, "cancelar")


def test_solo_participantes_y_rutas_protegidas(app, client, solicitud, publicacion):
    url = f"/objetos/prestamos/{solicitud}"
    assert client.get(url).status_code == 302
    login(client, 4)
    assert client.get(url).status_code == 404
    assert client.post(url + "/accion", data={"accion": "devolver"}).status_code == 404
    assert PUBLICACION["titulo"] not in client.get("/objetos/prestamos").text
    with app.app_context(), pytest.raises(PermissionError):
        prestamos.cambiar(solicitud, 4, "aceptar", fechas())
    login(client, 1)
    assert client.get("/objetos/prestamos").status_code == 403
    assert client.post(f"/objetos/{publicacion}/solicitar-prestamo", data=fechas()).status_code == 403
    login(client, 5)
    assert client.get(url).status_code == 403
    login(client, 3)
    assert client.get(f"/objetos/{publicacion}/solicitar-prestamo").status_code == 403


def test_formulario_seguimiento_listado_filtros_y_csrf(app, client, publicacion):
    login(client)
    url = f"/objetos/{publicacion}/solicitar-prestamo"
    assert "Pedir prestado" in client.get(f"/objetos/{publicacion}").text
    assert client.get(url).status_code == 200
    resultado = client.post(url, data=fechas(mensaje="Necesito practicar fotografía."))
    assert resultado.status_code == 302
    assert "Necesito practicar fotografía." in client.get(resultado.location).text
    assert client.get(url).location == resultado.location
    assert "Ver mi solicitud" in client.get(f"/objetos/{publicacion}").text
    assert PUBLICACION["titulo"] in client.get("/objetos/prestamos?estado=pendiente").text
    assert PUBLICACION["titulo"] not in client.get("/objetos/prestamos?estado=devuelto").text
    login(client, 3)
    assert PUBLICACION["titulo"] in client.get("/objetos/prestamos?vista=otorgados").text
    assert client.post(resultado.location + "/accion", data=fechas(accion="aceptar", condiciones="")).status_code == 400
    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post(resultado.location + "/accion", data=fechas(accion="aceptar")).status_code == 400
    assert client.post(url, data=fechas()).status_code == 400


def test_paginacion_y_filtros_invalidos(app, client):
    with app.app_context():
        for n in range(14):
            p = datos.crear(3, PUBLICACION | {"titulo": f"Cámara {n}"})
            prestamos.solicitar(p, 2, fechas())
    login(client)
    respuesta = client.get("/objetos/prestamos?vista=pedidos&estado=pendiente&pagina=2")
    assert respuesta.status_code == 200
    assert "Página 2 de 2" in respuesta.text
    assert "estado=pendiente" in respuesta.text
    assert client.get("/objetos/prestamos?pagina=abc&estado=inventado&vista=inventado").status_code == 200


@pytest.mark.parametrize("operacion", ["solicitar", "aceptar", "entregar", "devolver", "vencer"])
def test_notificacion_y_estado_son_atomicos(app, publicacion, monkeypatch, operacion):
    def falla(*args, **kwargs):
        raise RuntimeError("Avisos no disponibles")
    with app.app_context():
        sid = None
        if operacion != "solicitar":
            sid = prestamos.solicitar(publicacion, 2, fechas())
        if operacion in ("entregar", "devolver", "vencer"):
            prestamos.cambiar(sid, 3, "aceptar", fechas())
        if operacion in ("devolver", "vencer"):
            prestamos.cambiar(sid, 3, "entregar")
        previo = prestamos.obtener(sid) if sid else None
        monkeypatch.setattr(prestamos, "notificar", falla)
        with pytest.raises(RuntimeError):
            if operacion == "solicitar":
                prestamos.solicitar(publicacion, 2, fechas())
            elif operacion == "vencer":
                monkeypatch.setattr(prestamos, "hoy_local", lambda: "2026-11-03")
                prestamos.actualizar_vencidos()
            else:
                prestamos.cambiar(sid, 3, operacion, fechas())
        if previo:
            assert prestamos.obtener(sid) == previo
        else:
            assert db.query_one("SELECT count(*) AS n FROM prestamos")["n"] == 0


def test_migracion_preserva_prestamos_previos(tmp_path):
    ruta = tmp_path / "previa.db"
    with sqlite3.connect(ruta) as con:
        con.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY)")
        con.execute("CREATE TABLE prestamos (id INTEGER PRIMARY KEY, estado TEXT, condiciones TEXT)")
        con.execute("INSERT INTO prestamos VALUES (1, 'aceptado', 'Con cargador')")
    for _ in range(2):
        create_app({"DATABASE_URL": f"sqlite:///{ruta}"})
    with sqlite3.connect(ruta) as con:
        assert con.execute("SELECT estado, condiciones, mensaje, entregado FROM prestamos").fetchone() == (
            "aceptado", "Con cargador", "", None)
        assert con.execute("SELECT name FROM sqlite_master WHERE name='prestamos_movimientos'").fetchone()


def test_demo_es_aditivo_idempotente_y_preserva_c2(app):
    from davincihub.objetos import busquedas, prestamos_demo

    with app.app_context():
        p = datos.crear(3, PUBLICACION | {"titulo": "Mi anuncio C2"})
        busqueda, _ = busquedas.crear(2, {"titulo": "Cámara", "categoria": "foto_video"})
        assert prestamos_demo.cargar() == 6
        assert {pr["estado"] for pr in db.query("SELECT estado FROM prestamos")} == set(prestamos.ESTADOS)
        pr = db.query_one("SELECT id, publicacion_id FROM prestamos WHERE estado = 'pendiente'")
        prestamos.cambiar(pr["id"], 2, "rechazar")
        assert prestamos_demo.cargar() == 0
        assert prestamos.obtener(pr["id"])["estado"] == "cancelado"
        assert datos.obtener(p)["titulo"] == "Mi anuncio C2"
        assert busquedas.obtener(busqueda)["estado"] == "activa"
        assert db.query_one("SELECT count(*) AS n FROM prestamos")["n"] == 6


def test_prestamo_historico_sigue_accesible_con_publicacion_oculta(app, client, solicitud, publicacion):
    with app.app_context():
        prestamos.cambiar(solicitud, 3, "aceptar", fechas())
        prestamos.cambiar(solicitud, 3, "entregar")
        db.execute("UPDATE publicaciones SET oculto = 1 WHERE id = :id", id=publicacion)
    login(client)
    assert client.get(f"/objetos/prestamos/{solicitud}").status_code == 200
    assert client.get(f"/objetos/{publicacion}").status_code == 404
    login(client, 3)
    assert client.post(f"/objetos/prestamos/{solicitud}/accion", data={"accion": "devolver"}).status_code == 302


def test_bloqueo_del_solicitante_impide_aceptacion_y_entrega(app, solicitud):
    with app.app_context():
        db.execute("UPDATE usuarios SET bloqueado = 1 WHERE id = 2")
        with pytest.raises(prestamos.ErrorPrestamo):
            prestamos.cambiar(solicitud, 3, "aceptar", fechas())
        db.execute("UPDATE usuarios SET bloqueado = 0 WHERE id = 2")
        prestamos.cambiar(solicitud, 3, "aceptar", fechas())
        db.execute("UPDATE usuarios SET bloqueado = 1 WHERE id = 2")
        with pytest.raises(prestamos.ErrorPrestamo):
            prestamos.cambiar(solicitud, 3, "entregar")
        prestamos.cambiar(solicitud, 3, "cancelar")
        assert prestamos.obtener(solicitud)["estado"] == "cancelado"


def test_aceptaciones_simultaneas_no_prestan_dos_veces(app, solicitud, publicacion):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    with app.app_context():
        segunda = prestamos.solicitar(publicacion, 4, fechas())
    barrera = Barrier(2)

    def aceptar(sid):
        with app.app_context():
            barrera.wait(timeout=5)
            try:
                prestamos.cambiar(sid, 3, "aceptar", fechas())
                return "aceptado"
            except prestamos.ErrorPrestamo:
                return "ocupado"

    with ThreadPoolExecutor(max_workers=2) as equipo:
        resultados = list(equipo.map(aceptar, (solicitud, segunda)))
    assert sorted(resultados) == ["aceptado", "ocupado"]
    with app.app_context():
        assert db.query_one("SELECT count(*) AS n FROM prestamos WHERE estado = 'aceptado'")["n"] == 1
