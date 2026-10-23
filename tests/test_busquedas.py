import sqlite3

import pytest

from davincihub import db
from davincihub.app import create_app
from davincihub.objetos import busquedas, datos

BUSQUEDA = {"titulo": "Calculadora científica", "descripcion": "Para matemática",
            "categoria": "utiles", "modalidad": "venta", "presupuesto_max": "30000"}
PUBLICACION = {"titulo": "Calculadora Casio", "descripcion": "Funciona correctamente.",
               "categoria": "utiles", "estado_objeto": "usado_buen_estado",
               "modalidad": "venta", "precio": "25000", "carrera_id": ""}


@pytest.fixture(autouse=True)
def escenario(app):
    with app.app_context():
        for tabla in ("coincidencias", "solicitudes", "publicaciones", "notificaciones"):
            db.execute(f"DELETE FROM {tabla}")


@pytest.fixture
def estudiante(client):
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = 2
    return client


def test_busqueda_nueva_encuentra_publicacion_existente(app, estudiante):
    with app.app_context():
        datos.crear(3, PUBLICACION)
    respuesta = estudiante.post("/objetos/busquedas/nueva", data=BUSQUEDA)
    assert respuesta.status_code == 302
    detalle = estudiante.get(respuesta.location)
    assert detalle.status_code == 200
    assert "Calculadora Casio" in detalle.text
    assert "$30.000,00" in detalle.text
    with app.app_context():
        aviso = db.query_one("SELECT * FROM notificaciones")
        assert aviso["usuario_id"] == 2
        assert aviso["enlace"] == respuesta.location
        assert "posible coincidencia" in aviso["cuerpo"]


def test_publicacion_nueva_avisa_a_quien_busca(app):
    with app.app_context():
        solicitud, n = busquedas.crear(2, BUSQUEDA)
        assert n == 0
        publicacion = datos.crear(3, PUBLICACION)
        assert db.query_one("SELECT solicitud_id, publicacion_id FROM coincidencias") == {
            "solicitud_id": solicitud, "publicacion_id": publicacion,
        }
        assert db.query_one("SELECT usuario_id FROM notificaciones")["usuario_id"] == 2


@pytest.mark.parametrize("precio,espera", [("30000", 1), ("30000.01", 0), ("35000", 0)])
def test_limite_de_presupuesto(app, precio, espera):
    with app.app_context():
        datos.crear(3, PUBLICACION | {"precio": precio})
        _, n = busquedas.crear(2, BUSQUEDA)
        assert n == espera
        assert db.query_one("SELECT count(*) AS n FROM notificaciones")["n"] == espera


@pytest.mark.parametrize("busca", ["cualquiera", "venta", "intercambio", "prestamo"])
@pytest.mark.parametrize("ofrece", ["venta", "intercambio", "prestamo"])
def test_respeta_modalidad(app, busca, ofrece):
    with app.app_context():
        datos.crear(3, PUBLICACION | {"modalidad": ofrece})
        _, n = busquedas.crear(2, BUSQUEDA | {"modalidad": busca})
        assert n == int(busca in ("cualquiera", ofrece))


def test_compra_sin_limite_y_presupuesto_ignorado_fuera_de_compra(app):
    with app.app_context():
        datos.crear(3, PUBLICACION | {"precio": "90000"})
        solicitud, n = busquedas.crear(2, BUSQUEDA | {"presupuesto_max": ""})
        assert n == 1
        assert busquedas.obtener(solicitud)["presupuesto_max"] is None
        solicitud, _ = busquedas.crear(2, BUSQUEDA | {"modalidad": "prestamo"})
        assert busquedas.obtener(solicitud)["presupuesto_max"] is None


def test_categoria_y_palabras_son_necesarias(app):
    with app.app_context():
        datos.crear(3, PUBLICACION | {"categoria": "computacion"})
        datos.crear(3, PUBLICACION | {"titulo": "Carpeta A3", "descripcion": "Con elásticos."})
        assert busquedas.crear(2, BUSQUEDA)[1] == 0


def test_normaliza_acentos_mayusculas_y_no_busca_subcadenas(app):
    with app.app_context():
        datos.crear(3, PUBLICACION | {"titulo": "CIENTÍFICA", "descripcion": "Con pilas."})
        datos.crear(3, PUBLICACION | {"titulo": "Microcalculadora", "descripcion": "Con pilas."})
        solicitud, n = busquedas.crear(2, BUSQUEDA)
        assert n == 1
        assert busquedas.coincidencias_de(busquedas.obtener(solicitud))[0]["titulo"] == "CIENTÍFICA"


def test_coincide_por_caracteristicas_y_ignora_palabras_vacias(app):
    with app.app_context():
        datos.crear(3, PUBLICACION | {"titulo": "Casio", "descripcion": "Modelo científica"})
        assert busquedas.crear(2, BUSQUEDA | {"titulo": "Busco un equipo",
                                             "descripcion": "Calculadora científica"})[1] == 1
        assert busquedas.crear(2, BUSQUEDA | {"titulo": "Otra herramienta",
                                             "descripcion": "Para el curso con una"})[1] == 0


@pytest.mark.parametrize("cambios,campo", [
    ({"titulo": ""}, "titulo"), ({"titulo": "a" * 121}, "titulo"),
    ({"titulo": "para con una", "descripcion": ""}, "titulo"),
    ({"descripcion": "a" * 2001}, "descripcion"), ({"categoria": "ropa"}, "categoria"),
    ({"modalidad": "alquiler"}, "modalidad"),
    ({"presupuesto_max": "0"}, "presupuesto_max"),
    ({"presupuesto_max": "-10"}, "presupuesto_max"),
    ({"presupuesto_max": "NaN"}, "presupuesto_max"),
    ({"presupuesto_max": "Infinity"}, "presupuesto_max"),
    ({"presupuesto_max": "1000000000"}, "presupuesto_max"),
    ({"presupuesto_max": "1.001"}, "presupuesto_max"),
])
def test_valida_busqueda_sin_guardar_datos_invalidos(app, estudiante, cambios, campo):
    respuesta = estudiante.post("/objetos/busquedas/nueva", data=BUSQUEDA | cambios)
    assert respuesta.status_code == 400
    assert f'id="error-{campo}"' in respuesta.text
    with app.app_context():
        assert db.query_one("SELECT count(*) AS n FROM solicitudes")["n"] == 0


def test_no_avisa_por_publicaciones_propias(app):
    with app.app_context():
        datos.crear(2, PUBLICACION)
        solicitud, n = busquedas.crear(2, BUSQUEDA)
        datos.crear(2, PUBLICACION | {"titulo": "Otra calculadora"})
        assert n == 0
        assert busquedas.coincidencias_de(busquedas.obtener(solicitud)) == []
        assert db.query_one("SELECT count(*) AS n FROM notificaciones")["n"] == 0


def test_un_solo_aviso_aunque_se_recalcule_edite_o_reactive(app):
    with app.app_context():
        solicitud, _ = busquedas.crear(2, BUSQUEDA)
        publicacion = datos.crear(3, PUBLICACION)
        busquedas.detectar_para_busqueda(solicitud)
        busquedas.detectar_para_publicacion(publicacion)
        datos.editar(publicacion, 3, PUBLICACION | {"precio": "20000"})
        datos.cambiar_estado(publicacion, 3, "pausada")
        datos.cambiar_estado(publicacion, 3, "activa")
        assert db.query_one("SELECT count(*) AS n FROM coincidencias")["n"] == 1
        assert db.query_one("SELECT count(*) AS n FROM notificaciones")["n"] == 1


def test_cambio_de_precio_puede_generar_primera_coincidencia(app):
    with app.app_context():
        solicitud, _ = busquedas.crear(2, BUSQUEDA)
        publicacion = datos.crear(3, PUBLICACION | {"precio": "35000"})
        assert db.query_one("SELECT count(*) AS n FROM coincidencias")["n"] == 0
        datos.editar(publicacion, 3, PUBLICACION)
        assert len(busquedas.coincidencias_de(busquedas.obtener(solicitud))) == 1
        datos.editar(publicacion, 3, PUBLICACION | {"precio": "35000"})
        assert busquedas.coincidencias_de(busquedas.obtener(solicitud)) == []
        datos.editar(publicacion, 3, PUBLICACION)
        assert db.query_one("SELECT count(*) AS n FROM notificaciones")["n"] == 1


@pytest.mark.parametrize("estado", ["pausada", "cerrada"])
def test_no_muestra_ni_notifica_publicaciones_inactivas(app, estado):
    with app.app_context():
        publicacion = datos.crear(3, PUBLICACION)
        datos.cambiar_estado(publicacion, 3, estado)
        solicitud, n = busquedas.crear(2, BUSQUEDA)
        assert n == 0
        assert busquedas.coincidencias_de(busquedas.obtener(solicitud)) == []
        if estado == "pausada":
            datos.cambiar_estado(publicacion, 3, "activa")
            assert len(busquedas.coincidencias_de(busquedas.obtener(solicitud))) == 1


def test_coincidencia_previa_desaparece_si_la_publicacion_se_pausa(app):
    with app.app_context():
        publicacion = datos.crear(3, PUBLICACION)
        solicitud, _ = busquedas.crear(2, BUSQUEDA)
        datos.cambiar_estado(publicacion, 3, "pausada")
        assert busquedas.coincidencias_de(busquedas.obtener(solicitud)) == []


def test_bloqueados_no_generan_ni_reciben_coincidencias(app):
    with app.app_context():
        solicitud, _ = busquedas.crear(2, BUSQUEDA)
        db.execute("UPDATE usuarios SET bloqueado = 1 WHERE id = 2")
        publicacion = datos.crear(3, PUBLICACION)
        assert db.query_one("SELECT count(*) AS n FROM notificaciones")["n"] == 0
        db.execute("UPDATE usuarios SET bloqueado = 0 WHERE id = 2")
        db.execute("UPDATE usuarios SET bloqueado = 1 WHERE id = 3")
        assert busquedas.detectar_para_busqueda(solicitud) == 0
        assert busquedas.detectar_para_publicacion(publicacion) == 0


def test_cerrar_impide_nuevas_coincidencias_y_conserva_la_busqueda(app, estudiante):
    with app.app_context():
        solicitud, _ = busquedas.crear(2, BUSQUEDA)
    respuesta = estudiante.post(f"/objetos/busquedas/{solicitud}/cerrar")
    assert respuesta.status_code == 302
    with app.app_context():
        datos.crear(3, PUBLICACION)
        assert busquedas.obtener(solicitud)["estado"] == "cerrada"
        assert busquedas.detectar_para_busqueda(solicitud) == 0
        assert db.query_one("SELECT count(*) AS n FROM notificaciones")["n"] == 0
    assert "Calculadora científica" in estudiante.get("/objetos/busquedas?estado=cerrada").text
    assert "Calculadora científica" not in estudiante.get("/objetos/busquedas").text


def test_solicitudes_y_sus_coincidencias_son_privadas(app, client):
    with app.app_context():
        datos.crear(3, PUBLICACION)
        solicitud, _ = busquedas.crear(2, BUSQUEDA)
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = 3
    assert client.get(f"/objetos/busquedas/{solicitud}").status_code == 404
    assert client.post(f"/objetos/busquedas/{solicitud}/cerrar").status_code == 404
    assert "Calculadora científica" not in client.get("/objetos/busquedas").text
    with app.app_context():
        with pytest.raises(PermissionError):
            busquedas.cerrar(solicitud, 3)
        assert busquedas.obtener(solicitud)["estado"] == "activa"


@pytest.mark.parametrize("ruta", ["/objetos/busquedas", "/objetos/busquedas/nueva", "/objetos/busquedas/1"])
def test_busquedas_requieren_login(client, ruta):
    assert client.get(ruta).status_code == 302


@pytest.mark.parametrize("usuario", [1, 5])
def test_admin_y_bloqueado_no_crean_busquedas(app, client, usuario):
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = usuario
    assert client.post("/objetos/busquedas/nueva", data=BUSQUEDA).status_code == 403
    with app.app_context(), pytest.raises(PermissionError):
        busquedas.crear(usuario, BUSQUEDA)


def test_csrf_en_busqueda_y_cierre(app, estudiante):
    with app.app_context():
        solicitud, _ = busquedas.crear(2, BUSQUEDA)
    app.config["WTF_CSRF_ENABLED"] = True
    assert estudiante.post("/objetos/busquedas/nueva", data=BUSQUEDA).status_code == 400
    assert estudiante.post(f"/objetos/busquedas/{solicitud}/cerrar").status_code == 400


@pytest.mark.parametrize("operacion", ["busqueda", "publicacion"])
def test_fallo_de_notificacion_revierte_toda_la_operacion(app, monkeypatch, operacion):
    def falla(*args, **kwargs):
        raise RuntimeError("Servicio de avisos no disponible")

    with app.app_context():
        if operacion == "busqueda":
            datos.crear(3, PUBLICACION)
        else:
            busquedas.crear(2, BUSQUEDA)
        monkeypatch.setattr(busquedas, "notificar", falla)
        with pytest.raises(RuntimeError):
            busquedas.crear(2, BUSQUEDA) if operacion == "busqueda" else datos.crear(3, PUBLICACION)
        tabla = "solicitudes" if operacion == "busqueda" else "publicaciones"
        assert db.query_one(f"SELECT count(*) AS n FROM {tabla}")["n"] == 0
        assert db.query_one("SELECT count(*) AS n FROM coincidencias")["n"] == 0


def test_unicidad_de_coincidencias_en_la_base(app):
    with app.app_context():
        publicacion = datos.crear(3, PUBLICACION)
        solicitud, _ = busquedas.crear(2, BUSQUEDA)
        with pytest.raises(db.ErrorIntegridad):
            db.execute("INSERT INTO coincidencias (solicitud_id, publicacion_id, creado)"
                       " VALUES (:s, :p, 'hoy')", s=solicitud, p=publicacion)


def test_paginacion_de_mis_busquedas(app, estudiante):
    with app.app_context():
        for n in range(14):
            busquedas.crear(2, BUSQUEDA | {"titulo": f"Calculadora modelo {n}"})
        resultado = busquedas.listar_de(2, pagina=2)
        assert resultado["total"] == 14
        assert len(resultado["solicitudes"]) == 2
    assert "Página 2 de 2" in estudiante.get("/objetos/busquedas?pagina=2").text
    assert estudiante.get("/objetos/busquedas?pagina=abc&estado=invalido").status_code == 200


def test_migracion_conserva_solicitudes_previas(tmp_path):
    ruta = tmp_path / "previa.db"
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY)")
        conexion.execute("CREATE TABLE solicitudes (id INTEGER PRIMARY KEY, titulo TEXT, presupuesto_max REAL)")
        conexion.execute("INSERT INTO solicitudes VALUES (1, 'Calculadora', 30000)")
    for _ in range(2):
        create_app({"DATABASE_URL": f"sqlite:///{ruta}"})
    with sqlite3.connect(ruta) as conexion:
        assert conexion.execute("SELECT titulo, presupuesto_max, modalidad FROM solicitudes").fetchone() == (
            "Calculadora", 30000, "cualquiera",
        )
        assert conexion.execute("SELECT name FROM sqlite_master WHERE name='coincidencias'").fetchone()


@pytest.mark.parametrize("titulo", ["calculador", "CALCULADOR", "calculadora cientifica", "CALCULADORA CIENTÍFICA"])
def test_prefijo_mayusculas_y_tildes_encuentran_calculadora(app, titulo):
    with app.app_context():
        publicacion = datos.crear(3, PUBLICACION)
        solicitud, cantidad = busquedas.crear(2, BUSQUEDA | {"titulo": titulo})
        assert cantidad == 1
        assert busquedas.coincidencias_de(busquedas.obtener(solicitud))[0]["id"] == publicacion


def test_prefijo_no_coincide_en_medio_de_palabra(app):
    with app.app_context():
        datos.crear(3, PUBLICACION | {"titulo": "Microcalculadora", "descripcion": "Con pilas."})
        assert busquedas.crear(2, BUSQUEDA | {"titulo": "calculador", "descripcion": ""})[1] == 0


def test_todas_las_categorias_revisa_existentes_y_nuevas_sin_duplicar(app):
    with app.app_context():
        datos.crear(3, PUBLICACION | {"categoria": "computacion"})
        solicitud, cantidad = busquedas.crear(2, BUSQUEDA | {"categoria": "todas"})
        assert cantidad == 1
        datos.crear(3, PUBLICACION | {"categoria": "libros_apuntes"})
        assert len(busquedas.coincidencias_de(busquedas.obtener(solicitud))) == 2
        assert busquedas.detectar_para_busqueda(solicitud) == 0
        assert db.query_one("SELECT count(*) AS n FROM notificaciones")["n"] == 2
        datos.crear(2, PUBLICACION)
        datos.crear(3, PUBLICACION | {"precio": "30001"})
        assert len(busquedas.coincidencias_de(busquedas.obtener(solicitud))) == 2
