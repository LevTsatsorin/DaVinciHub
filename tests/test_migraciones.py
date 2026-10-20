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
