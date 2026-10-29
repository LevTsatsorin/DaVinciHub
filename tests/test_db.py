import pytest

from davincihub import db

TABLAS = {
    "carreras",
    "materias",
    "usuarios",
    "fotos_perfil",
    "bloqueos",
    "conexiones",
    "preguntas",
    "respuestas",
    "valoraciones_respuestas",
    "publicaciones",
    "solicitudes",
    "prestamos",
    "intercambios",
    "ventas",
    "valoraciones_operaciones",
    "espacios",
    "horarios_espacios",
    "reservas",
    "actividades",
    "inscripciones",
    "mensajes",
    "notificaciones",
    "reportes",
}


def test_init_db_crea_tablas(app):
    with app.app_context():
        db.init_db()
        filas = db.query("SELECT name FROM sqlite_master WHERE type = :tipo", tipo="table")
        nombres = {fila["name"] for fila in filas}
        assert TABLAS <= nombres, TABLAS - nombres


def test_demo_tiene_admin(app):
    with app.app_context():
        db.init_db(demo=True)
        admin = db.query_one("SELECT * FROM usuarios WHERE rol = :rol", rol="admin")
        assert admin is not None
        assert admin["bloqueado"] == 0


def test_migracion_fotos_perfil_es_idempotente(app):
    with app.app_context():
        db.execute("DROP TABLE fotos_perfil")
        db.migrar()
        db.migrar()
        tablas = db.query("SELECT name FROM sqlite_master WHERE type = :tipo", tipo="table")
        assert "fotos_perfil" in {fila["name"] for fila in tablas}


def _insertar_usuario(email):
    return db.execute(
        "INSERT INTO usuarios (nombre, apellido, email, password_hash, creado)"
        " VALUES (:nombre, :apellido, :email, :hash, :creado)",
        nombre="Otro",
        apellido="Usuario",
        email=email,
        hash="x",
        creado="2026-10-18T00:00:00",
    )


def test_email_unico(app):
    with app.app_context():
        assert _insertar_usuario("libre@davinci.edu.ar") == 1
        with pytest.raises(db.ErrorIntegridad):
            _insertar_usuario("libre@davinci.edu.ar")


def test_insertar_devuelve_id(app):
    with app.app_context():
        db.init_db()
        fila = db.query_one(
            "INSERT INTO carreras (nombre) VALUES (:nombre) RETURNING id",
            nombre="Diseño Multimedial",
        )
        assert fila["id"] >= 1


def test_a_psycopg_traduce_parametros():
    assert db._a_psycopg("SELECT :a, :b") == "SELECT %(a)s, %(b)s"


def test_a_psycopg_escapa_porcentaje():
    assert db._a_psycopg("LIKE '%' || :q || '%'") == "LIKE '%%' || %(q)s || '%%'"


def test_transaccion_revierte(app):
    with app.app_context():
        with pytest.raises(RuntimeError), db.transaccion():
            db.execute("INSERT INTO carreras (nombre) VALUES (:nombre)", nombre="Temporal")
            raise RuntimeError("boom")
        assert db.query_one("SELECT id FROM carreras WHERE nombre = :nombre", nombre="Temporal") is None


def test_init_db_postgres_crea_tablas():
    import os

    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("sin TEST_DATABASE_URL")
    from davincihub.app import create_app

    aplicacion = create_app({"TESTING": True, "DATABASE_URL": url})
    with aplicacion.app_context():
        db.init_db()
        filas = db.query(
            "SELECT table_name AS name FROM information_schema.tables"
            " WHERE table_schema = 'public'"
        )
        assert TABLAS <= {fila["name"] for fila in filas}


def test_demo_carreras_completas(app):
    with app.app_context():
        carreras = db.query("SELECT * FROM carreras")
        assert len(carreras) == 8
        assert all(fila["duracion_anios"] in (2, 3) for fila in carreras)
        huerfanas = db.query_one(
            "SELECT count(*) AS n FROM materias WHERE cuatrimestre IS NULL"
        )
        assert huerfanas["n"] == 0
        total = db.query_one("SELECT count(*) AS n FROM materias")
        assert total["n"] > 200


def test_a_psycopg_respeta_literales():
    sql = "SELECT 'hola:mundo' AS t, '10:00' AS h WHERE x = :y"
    assert db._a_psycopg(sql) == "SELECT 'hola:mundo' AS t, '10:00' AS h WHERE x = %(y)s"


def test_a_psycopg_literal_con_comilla_escapada():
    sql = "SELECT 'it''s :no' AS t, :si AS u"
    assert db._a_psycopg(sql) == "SELECT 'it''s :no' AS t, %(si)s AS u"


def test_transaccion_anidada_revierte_todo(app):
    with app.app_context():
        with pytest.raises(RuntimeError), db.transaccion():
            db.execute("INSERT INTO carreras (nombre) VALUES (:nombre)", nombre="Externa")
            with db.transaccion():
                db.execute("INSERT INTO carreras (nombre) VALUES (:nombre)", nombre="Interna")
            raise RuntimeError("boom")
        nombres = {f["nombre"] for f in db.query("SELECT nombre FROM carreras")}
        assert "Externa" not in nombres
        assert "Interna" not in nombres


def test_bloquear_fila_exige_transaccion(app):
    with app.app_context(), pytest.raises(RuntimeError):
        db.bloquear_fila("espacios", 1)


def test_bloquear_fila_indica_si_existe(app):
    with app.app_context(), db.transaccion():
        assert db.bloquear_fila("espacios", 1) is True
        assert db.bloquear_fila("espacios", 999) is False


def test_bloquear_fila_rechaza_tabla_invalida(app):
    with app.app_context(), db.transaccion(), pytest.raises(ValueError):
        db.bloquear_fila("espacios; DROP TABLE usuarios", 1)


def test_postgres_detalle_objeto_y_ocupacion_sin_exclusion():
    import os

    from davincihub.app import create_app
    from davincihub.objetos import datos, prestamos
    from davincihub.utiles import ahora

    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("sin TEST_DATABASE_URL")
    aplicacion = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "DATABASE_URL": url})
    with aplicacion.app_context():
        # Solo TEST_DATABASE_URL: esta base es de pruebas y puede reinicializarse.
        db.init_db(demo=True)
        publicacion = datos.crear(3, {
            "titulo": "Cámara para verificar PostgreSQL", "descripcion": "Con batería y cargador.",
            "categoria": "foto_video", "estado_objeto": "usado_buen_estado", "modalidad": "prestamo",
        })
        assert not prestamos.ocupado(publicacion)
        prestamo = db.query_one(
            "INSERT INTO prestamos (publicacion_id, solicitante_id, estado, creado)"
            " VALUES (:publicacion, 2, 'aceptado', :creado) RETURNING id",
            publicacion=publicacion, creado=ahora(),
        )["id"]
        assert prestamos.ocupado(publicacion)
        assert not prestamos.ocupado(publicacion, excepto=prestamo)
    cliente = aplicacion.test_client()
    with cliente.session_transaction() as sesion:
        sesion["usuario_id"] = 2
    respuesta = cliente.get(f"/objetos/{publicacion}")
    assert respuesta.status_code == 200
    assert "Cámara para verificar PostgreSQL" in respuesta.text


def test_postgres_c4_migracion_y_ciclos_completos():
    import os

    from davincihub.app import create_app
    from davincihub.objetos import acuerdos, datos

    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("sin TEST_DATABASE_URL")
    aplicacion = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "DATABASE_URL": url})
    with aplicacion.app_context():
        # Solo una base de pruebas desechable; nunca DATABASE_URL de producción.
        db.init_db(demo=True)
        publicaciones = db.query_one("SELECT count(*) AS n FROM publicaciones")["n"]
        for tabla, columna, _ in db.COLUMNAS_AGREGADAS:
            if tabla in ("ventas", "intercambios"):
                db.execute(f"ALTER TABLE {tabla} DROP COLUMN {columna}")
        db.execute("DROP TABLE acuerdos_movimientos")
        db.migrar()
        db.migrar()
        assert db.query_one("SELECT count(*) AS n FROM publicaciones")["n"] == publicaciones
        for tipo in ("venta", "intercambio"):
            pid = datos.crear(3, {
                "titulo": f"Material PostgreSQL {tipo}", "descripcion": "Material para estudiar.",
                "categoria": "dibujo_diseno", "estado_objeto": "usado_buen_estado",
                "modalidad": tipo, "precio": "30000",
            })
            form = {"oferta": "Ofrezco un libro de diseño.", "precio_acordado": "25000"}
            _, aid = acuerdos.proponer(pid, 2, form)
            _, competidor = acuerdos.proponer(pid, 4, form)
            acuerdos.cambiar(tipo, aid, 3, "aceptar")
            assert acuerdos.obtener(tipo, competidor)["estado"] == "cancelado"
            acuerdos.cambiar(tipo, aid, 2, "confirmar")
            assert acuerdos.obtener(tipo, aid)["estado"] == "aceptado"
            acuerdos.cambiar(tipo, aid, 3, "confirmar")
            assert acuerdos.obtener(tipo, aid)["estado"] == "completado"
            assert datos.obtener(pid)["estado"] == "cerrada"
            assert acuerdos.movimientos(tipo, aid)[-1]["estado_nuevo"] == "completado"
            assert acuerdos.listar(2, tipo=tipo, estado="completado")["total"] == 1
            cliente = aplicacion.test_client()
            with cliente.session_transaction() as sesion:
                sesion["usuario_id"] = 2
            for ruta in ("/objetos/acuerdos", f"/objetos/acuerdos/{tipo}/{aid}"):
                assert cliente.get(ruta).status_code == 200
            assert cliente.get(f"/objetos/{pid}").status_code == 404  # Cerrada: solo su dueño.
            with cliente.session_transaction() as sesion:
                sesion["usuario_id"] = 3
            assert cliente.get(f"/objetos/{pid}").status_code == 200
