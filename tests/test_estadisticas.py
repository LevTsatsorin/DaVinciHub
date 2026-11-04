"""C6: cifras verificables, privacidad y límites de la semana local."""
import os
from datetime import date

import pytest

from davincihub import db, estadisticas
from davincihub.app import create_app

HOY = date(2026, 11, 4)
FECHA = "2026-11-02T14:00:00+00:00"
SECRETO = "MENSAJE_PRIVADO_NO_DEBE_SALIR_7129"


def insertar(tabla, **valores):
    campos = ", ".join(valores)
    parametros = ", ".join(":" + clave for clave in valores)
    return db.query_one(f"INSERT INTO {tabla} ({campos}) VALUES ({parametros}) RETURNING id", **valores)["id"]


def escenario():
    db.init_db()
    carrera = insertar("carreras", nombre="Diseño")
    materia = insertar("materias", carrera_id=carrera, nombre="Taller")
    ids = [insertar("usuarios", nombre=nombre, apellido="Demo", email=nombre + "@davinci.edu.ar",
                    password_hash="x", rol=rol, creado=FECHA)
           for nombre, rol in (("Admin", "admin"), ("Ana", "estudiante"), ("Bea", "estudiante"))]
    admin, ana, bea = ids
    def publicacion(titulo, modalidad="venta", oculto=0):
        return insertar("publicaciones", autor_id=ana, titulo=titulo, descripcion="Descripción",
                        categoria="dibujo_diseno", estado_objeto="usado_buen_estado", modalidad=modalidad,
                        estado="cerrada", precio=100, oculto=oculto, creado=FECHA)
    venta = publicacion("Vendo")
    inter = publicacion("Cambio", "intercambio")
    ofrecida = publicacion("Ofrezco", "intercambio")
    prestado = publicacion("Presto", "prestamo")
    oculta = publicacion("Oculta", oculto=1)
    pregunta = insertar("preguntas", autor_id=ana, materia_id=materia, titulo="Visible", cuerpo="Hola", creado=FECHA)
    pregunta_oculta = insertar("preguntas", autor_id=ana, materia_id=materia, titulo="Oculta", cuerpo="Hola", creado=FECHA, oculto=1)
    respuesta = insertar("respuestas", pregunta_id=pregunta, autor_id=bea, cuerpo="Respuesta", creado=FECHA)
    for pid, oculto in ((pregunta, 1), (pregunta_oculta, 0)):
        insertar("respuestas", pregunta_id=pid, autor_id=bea, cuerpo="No contar", creado=FECHA, oculto=oculto)
    insertar("valoraciones_respuestas", respuesta_id=respuesta, usuario_id=ana, creado=FECHA)
    espacio = insertar("espacios", nombre="Sala")
    reservas = [insertar("reservas", espacio_id=espacio, usuario_id=ana, inicio="2026-11-05T10:00:00",
                         fin="2026-11-05T11:00:00", estado=estado, creado=FECHA)
                for estado in ("confirmada", "cancelada", "confirmada")]
    actividad = insertar("actividades", creador_id=ana, nombre="Visible", descripcion="Actividad",
                         inicio="2026-11-05T10:00:00", ubicacion="Sala", cupo_maximo=10,
                         estado="aprobada", reserva_id=reservas[0], creado=FECHA)
    actividad_oculta = insertar("actividades", creador_id=ana, nombre="Oculta", descripcion="Actividad",
                                inicio="2026-11-05T10:00:00", ubicacion="Sala", cupo_maximo=10,
                                estado="aprobada", reserva_id=reservas[2], oculto=1, creado=FECHA)
    for aid in (actividad, actividad_oculta):
        insertar("inscripciones", actividad_id=aid, usuario_id=bea, creado=FECHA)
    for _ in range(2):
        insertar("mensajes", emisor_id=ana, receptor_id=bea, cuerpo=SECRETO, creado=FECHA)
    insertar("conexiones", solicitante_id=ana, receptor_id=bea, estado="aceptada", creado=FECHA)
    insertar("conexiones", solicitante_id=admin, receptor_id=ana, estado="pendiente", creado=FECHA)
    for estado in ("devuelto", "cancelado"):
        insertar("prestamos", publicacion_id=prestado, solicitante_id=bea, estado=estado, devuelto=FECHA if estado == "devuelto" else None, creado=FECHA)
    insertar("ventas", publicacion_id=venta, comprador_id=bea, estado="completada", completado=FECHA, creado=FECHA)
    insertar("ventas", publicacion_id=oculta, comprador_id=bea, estado="completada", completado=FECHA, creado=FECHA)
    iid = insertar("intercambios", publicacion_id=inter, solicitante_id=bea, publicacion_ofrecida_id=ofrecida,
                   oferta="Libro", estado="completado", completado=FECHA, creado=FECHA)
    insertar("valoraciones_operaciones", tipo_operacion="intercambio", operacion_id=iid, autor_id=ana,
             receptor_id=bea, valor=5, comentario="Bien", creado=FECHA)
    insertar("solicitudes", autor_id=ana, titulo="Busco", categoria="todas", estado="cerrada", creado=FECHA)
    return {"admin": admin, "ana": ana, "bea": bea, "oculta": oculta, "ofrecida": ofrecida,
            "pregunta": pregunta, "materia": materia, "intercambio": iid}


@pytest.fixture
def muestra(app):
    with app.app_context():
        return escenario()


def entrar(client, usuario):
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = usuario


ESPERADOS = {"usuarios": 3, "publicaciones": 4, "preguntas": 1, "respuestas": 1,
             "reservas": 2, "actividades": 1, "mensajes": 2, "conexiones": 1,
             "propuestas": 4, "prestamos": 1, "ventas": 1, "intercambios": 1,
             "opiniones": 1, "utiles": 1, "inscripciones": 1, "busquedas": 1}


def test_totales_exactos_y_semanas_consistentes(app, muestra):
    with app.app_context():
        resultado = estadisticas.resumen(4, HOY)
    assert resultado["totales"] == ESPERADOS
    assert len(resultado["evolucion"]) == 4
    assert resultado["evolucion"][-1] == {"inicio": date(2026, 11, 2), "fin": HOY,
                                             "registros": 3, "contenidos": 9, "interacciones": 14}
    assert all(s["registros"] == s["contenidos"] == s["interacciones"] == 0 for s in resultado["evolucion"][:-1])
    assert resultado["materias"][0]["cantidad"] == 1
    assert resultado["categorias"][0]["cantidad"] == 4


def test_acceso_admin_login_estudiante_bloqueado(app, client, muestra):
    assert client.get("/admin/estadisticas/").status_code == 302
    entrar(client, muestra["ana"])
    assert client.get("/admin/estadisticas/").status_code == 403
    entrar(client, muestra["admin"])
    r = client.get("/admin/estadisticas/")
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "private, no-store"
    with app.app_context():
        db.execute("UPDATE usuarios SET bloqueado = 1 WHERE id = :id", id=muestra["admin"])
    assert client.get("/admin/estadisticas/").status_code == 403


def test_mensajes_solo_agregados_sin_texto_o_participantes(app, client, muestra, monkeypatch):
    consultas = []
    original = db.query
    def registrar(sql, **params):
        consultas.append(sql)
        return original(sql, **params)
    monkeypatch.setattr(db, "query", registrar)
    entrar(client, muestra["admin"])
    respuesta = client.get("/admin/estadisticas/")
    assert SECRETO not in respuesta.text
    assert "Ana Demo" not in respuesta.text and "Bea Demo" not in respuesta.text
    assert "Mensajes enviados" in respuesta.text
    sql_mensajes = [sql for sql in consultas if "FROM mensajes m" in sql]
    assert len(sql_mensajes) == 2
    assert all("m.cuerpo" not in sql and "m.emisor_id" not in sql and "m.receptor_id" not in sql
               and "SELECT m.*" not in sql for sql in sql_mensajes)


def test_moderacion_posterior_excluye_relaciones_y_semanas(app, muestra):
    with app.app_context():
        db.execute("UPDATE publicaciones SET oculto = 1 WHERE id = :id", id=muestra["ofrecida"])
        db.execute("UPDATE preguntas SET oculto = 1 WHERE id = :id", id=muestra["pregunta"])
        r = estadisticas.resumen(4, HOY)
    for clave in ("intercambios", "opiniones", "preguntas", "respuestas", "utiles"):
        assert r["totales"][clave] == 0
    assert r["totales"]["propuestas"] == 3
    assert r["totales"]["publicaciones"] == 3
    assert r["materias"] == []
    assert r["evolucion"][-1]["contenidos"] == 6
    assert r["evolucion"][-1]["interacciones"] == 10


def test_limites_lunes_local_utc_z_y_fechas_sin_zona(app):
    with app.app_context():
        db.init_db()
        for n, creado in enumerate(("2026-11-02T02:59:59+00:00", "2026-11-02T03:00:00+00:00",
                                   "2026-11-02T02:59:59Z", "2026-11-02T03:00:00Z",
                                   "2026-11-02T00:00:00", "2026-11-09T03:00:00+00:00",
                                   "2026-10-05T12:00:00+00:00")):
            insertar("usuarios", nombre="U", apellido="Demo", email=f"{n}@demo", password_hash="x", creado=creado)
        r = estadisticas.resumen(4, HOY)
    assert r["totales"]["usuarios"] == 7
    assert r["evolucion"][-1]["registros"] == 3
    assert r["evolucion"][-2]["registros"] == 2
    assert sum(s["registros"] for s in r["evolucion"]) == 5


def test_fecha_finalizacion_no_se_confunde_con_creacion(app, muestra):
    with app.app_context():
        db.execute("UPDATE ventas SET creado = '2026-10-19T12:00:00+00:00', completado = :fin", fin=FECHA)
        r = estadisticas.resumen(4, HOY)
    assert r["evolucion"][-3]["interacciones"] == 1  # Propuesta visible creada esa semana.
    assert r["evolucion"][-1]["interacciones"] == 13  # Incluye su finalización, excluye su creación.


@pytest.mark.parametrize("valor,esperado", [("4", 4), ("8", 8), ("12", 12), ("-1", 8), ("abc", 8), ("9" * 1000, 8)])
def test_periodo_validado(app, client, muestra, valor, esperado, monkeypatch):
    original = estadisticas.resumen
    periodos = []
    def registrar(semanas):
        periodos.append(semanas)
        return original(semanas, HOY)
    monkeypatch.setattr(estadisticas, "resumen", registrar)
    entrar(client, muestra["admin"])
    assert client.get("/admin/estadisticas/", query_string={"semanas": valor}).status_code == 200
    assert periodos == [esperado]


def test_base_vacia_y_rankings_empatados_separan_carreras(app):
    with app.app_context():
        db.init_db()
        r = estadisticas.resumen(4, HOY)
        assert not any(r["totales"].values())
        assert r["materias"] == r["categorias"] == [] and r["maximo"] == 1
        ids = escenario()
        for n in range(7):
            cid = insertar("carreras", nombre=f"Carrera {n}")
            mid = insertar("materias", carrera_id=cid, nombre="Taller")
            insertar("preguntas", autor_id=ids["ana"], materia_id=mid, titulo="Otra", cuerpo="Hola", creado=FECHA)
        r = estadisticas.resumen(4, HOY)
    assert len(r["materias"]) == 5
    assert len({m["id"] for m in r["materias"]}) == 5
    assert [m["carrera"] for m in r["materias"]] == [f"Carrera {n}" for n in range(5)]


def test_menu_y_cabecera_solo_admin(app, client, muestra):
    entrar(client, muestra["admin"])
    pagina = client.get("/admin/estadisticas/").text
    assert 'img/admin.png' in pagina and 'Ver cifras por semana' in pagina
    assert '/admin/estadisticas/' in client.get("/").text
    entrar(client, muestra["ana"])
    assert '/admin/estadisticas/' not in client.get("/").text


def test_postgres_estadisticas_y_privacidad():
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("sin TEST_DATABASE_URL")
    aplicacion = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "DATABASE_URL": url})
    with aplicacion.app_context():
        ids = escenario()  # Únicamente una base de pruebas desechable.
        r = estadisticas.resumen(4, HOY)
        assert r["totales"] == ESPERADOS
        assert r["evolucion"][-1]["contenidos"] == 9
        assert r["evolucion"][-1]["interacciones"] == 14
        insertar("mensajes", emisor_id=ids["ana"], receptor_id=ids["bea"], cuerpo=SECRETO,
                 creado="2026-11-02T02:59:59Z")
        r = estadisticas.resumen(4, HOY)
        assert r["evolucion"][-2]["interacciones"] == 1
    cliente = aplicacion.test_client()
    entrar(cliente, ids["admin"])
    respuesta = cliente.get("/admin/estadisticas/")
    assert respuesta.status_code == 200 and SECRETO not in respuesta.text


def test_cifras_coinciden_con_demo_del_proyecto(app):
    with app.app_context():
        resultado = estadisticas.resumen(8, HOY)
    assert resultado["totales"] == {
        "usuarios": 6, "publicaciones": 10, "preguntas": 3, "respuestas": 4,
        "reservas": 17, "actividades": 15, "mensajes": 4, "conexiones": 0,
        "propuestas": 0, "prestamos": 0, "ventas": 0, "intercambios": 0,
        "opiniones": 0, "utiles": 0, "inscripciones": 12, "busquedas": 0,
    }
