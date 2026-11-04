import sqlite3

from davincihub import db
from davincihub.app import create_app


def _columnas(ruta, tabla):
    with sqlite3.connect(ruta) as conexion:
        return {fila[1] for fila in conexion.execute(f"PRAGMA table_info({tabla})")}


def test_al_arrancar_agrega_las_columnas_nuevas(tmp_path):
    ruta = tmp_path / "vieja.db"
    with sqlite3.connect(ruta) as conexion:
        conexion.execute(
            "CREATE TABLE reservas (id INTEGER PRIMARY KEY, espacio_id INTEGER, usuario_id INTEGER,"
            " inicio TEXT, fin TEXT, estado TEXT, creado TEXT)"
        )
        conexion.execute("INSERT INTO reservas VALUES (1, 1, 1, 'a', 'b', 'confirmada', 'c')")
    create_app({"DATABASE_URL": f"sqlite:///{ruta}"})
    assert {"motivo", "personas"} <= _columnas(ruta, "reservas")
    with sqlite3.connect(ruta) as conexion:
        assert conexion.execute("SELECT motivo, personas FROM reservas").fetchone() == ("", None)


def test_arrancar_dos_veces_no_falla(tmp_path):
    url = f"sqlite:///{tmp_path}/doble.db"
    app = create_app({"DATABASE_URL": url})
    with app.app_context():
        db.init_db()
    create_app({"DATABASE_URL": url})
    create_app({"DATABASE_URL": url})


def test_arrancar_sin_tablas_no_crea_nada(tmp_path):
    ruta = tmp_path / "vacia.db"
    create_app({"DATABASE_URL": f"sqlite:///{ruta}"})
    assert _columnas(ruta, "reservas") == set()


def test_al_arrancar_crea_las_tablas_nuevas(tmp_path):
    ruta = tmp_path / "sin_bloqueos.db"
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, bloqueado INTEGER)")
    create_app({"DATABASE_URL": f"sqlite:///{ruta}"})
    assert {"usuario_id", "admin_id", "accion", "motivo", "creado"} <= _columnas(ruta, "bloqueos")


def test_al_arrancar_crea_los_indices_nuevos(tmp_path):
    ruta = tmp_path / "sin_indice.db"
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, bloqueado INTEGER)")
    create_app({"DATABASE_URL": f"sqlite:///{ruta}"})
    with sqlite3.connect(ruta) as conexion:
        indices = {fila[1] for fila in conexion.execute("PRAGMA index_list(bloqueos)")}
    assert "idx_bloqueos_usuario" in indices


def test_al_arrancar_garantiza_una_respuesta_aceptada_por_pregunta(tmp_path):
    ruta = tmp_path / "foro_sin_indice.db"
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, bloqueado INTEGER)")
        conexion.execute(
            "CREATE TABLE respuestas (id INTEGER PRIMARY KEY, pregunta_id INTEGER, aceptada INTEGER)"
        )
    create_app({"DATABASE_URL": f"sqlite:///{ruta}"})
    with sqlite3.connect(ruta) as conexion:
        indices = {fila[1] for fila in conexion.execute("PRAGMA index_list(respuestas)")}
    assert "idx_respuesta_aceptada" in indices


def test_al_arrancar_agrega_imagenes_y_respuestas_en_hilo(tmp_path):
    ruta = tmp_path / "foro_anterior.db"
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, bloqueado INTEGER)")
        conexion.execute("CREATE TABLE preguntas (id INTEGER PRIMARY KEY)")
        conexion.execute(
            "CREATE TABLE respuestas (id INTEGER PRIMARY KEY, pregunta_id INTEGER, aceptada INTEGER)"
        )
    create_app({"DATABASE_URL": f"sqlite:///{ruta}"})
    assert {"imagen_tipo", "imagen"} <= _columnas(ruta, "preguntas")
    assert "respuesta_padre_id" in _columnas(ruta, "respuestas")
def test_al_arrancar_indexa_los_mensajes_existentes(tmp_path):
    ruta = tmp_path / "mensajes_sin_indice.db"
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, bloqueado INTEGER)")
        conexion.execute(
            "CREATE TABLE mensajes (id INTEGER PRIMARY KEY, emisor_id INTEGER, receptor_id INTEGER,"
            " cuerpo TEXT, leido INTEGER, creado TEXT)"
        )
    create_app({"DATABASE_URL": f"sqlite:///{ruta}"})
    with sqlite3.connect(ruta) as conexion:
        indices = {fila[1] for fila in conexion.execute("PRAGMA index_list(mensajes)")}
    assert "idx_mensajes_conversacion" in indices


def test_al_arrancar_agrega_la_gamma_del_chat(tmp_path):
    ruta = tmp_path / "usuarios_viejos.db"
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, bloqueado INTEGER)")
        conexion.execute("INSERT INTO usuarios VALUES (1, 0)")
    create_app({"DATABASE_URL": f"sqlite:///{ruta}"})
    with sqlite3.connect(ruta) as conexion:
        assert conexion.execute("SELECT chat_tema FROM usuarios").fetchone() == ("davinci",)


def test_al_arrancar_consolida_solicitudes_mutuas_y_evitas_pares_duplicados(tmp_path):
    ruta = tmp_path / "conexiones_anteriores.db"
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, bloqueado INTEGER)")
        conexion.execute(
            "CREATE TABLE conexiones (id INTEGER PRIMARY KEY, solicitante_id INTEGER, receptor_id INTEGER,"
            " estado TEXT, creado TEXT, UNIQUE (solicitante_id, receptor_id))"
        )
        conexion.executemany(
            "INSERT INTO conexiones VALUES (?, ?, ?, 'pendiente', '2026-10-20')",
            [(1, 2, 3), (2, 3, 2)],
        )
    create_app({"DATABASE_URL": f"sqlite:///{ruta}"})
    with sqlite3.connect(ruta) as conexion:
        filas = conexion.execute(
            "SELECT solicitante_id, receptor_id, estado FROM conexiones"
        ).fetchall()
        indices = {fila[1] for fila in conexion.execute("PRAGMA index_list(conexiones)")}
    assert filas == [(2, 3, "aceptada")]
    assert "idx_conexiones_par" in indices
    with sqlite3.connect(ruta) as conexion:
        try:
            conexion.execute(
                "INSERT INTO conexiones VALUES (3, 3, 2, 'pendiente', '2026-10-21')"
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("El índice debe impedir pares de conexión invertidos duplicados.")
