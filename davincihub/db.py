import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import click
from flask import current_app, g


class ErrorIntegridad(Exception):
    pass


def _es_postgres(url: str) -> bool:
    return url.startswith(("postgres://", "postgresql://"))


_LITERAL_O_PARAMETRO = re.compile(r"'(?:[^']|'')*'|(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)")


def _a_psycopg(sql: str) -> str:
    sql = sql.replace("%", "%%")
    return _LITERAL_O_PARAMETRO.sub(
        lambda m: f"%({m.group(1)})s" if m.group(1) else m.group(0), sql
    )


def get_db():
    if "db" not in g:
        url = current_app.config.get("DATABASE_URL", "")
        if _es_postgres(url):
            import psycopg
            from psycopg.rows import dict_row

            g.db = psycopg.connect(url, row_factory=dict_row)
            g.db_es_pg = True
        else:
            ruta = url.removeprefix("sqlite:///")
            if not ruta:
                ruta = os.path.join(current_app.instance_path, "davincihub.db")
            Path(ruta).parent.mkdir(parents=True, exist_ok=True)
            conexion = sqlite3.connect(ruta, isolation_level=None)
            conexion.row_factory = sqlite3.Row
            conexion.execute("PRAGMA foreign_keys = ON")
            g.db = conexion
            g.db_es_pg = False
    return g.db


def close_db(e=None):
    conexion = g.pop("db", None)
    if conexion is not None:
        conexion.close()


def _ejecutar(sql: str, params: dict):
    conexion = get_db()
    if g.db_es_pg:
        import psycopg

        try:
            return conexion.execute(_a_psycopg(sql), params)
        except psycopg.errors.IntegrityError as error:
            conexion.rollback()
            raise ErrorIntegridad(str(error)) from error
    try:
        return conexion.execute(sql, params)
    except sqlite3.IntegrityError as error:
        raise ErrorIntegridad(str(error)) from error


def _confirmar():
    if not g.get("en_transaccion"):
        get_db().commit()


def query(sql: str, **params) -> list[dict]:
    cursor = _ejecutar(sql, params)
    filas = [dict(fila) for fila in cursor.fetchall()]
    _confirmar()
    return filas


def query_one(sql: str, **params) -> dict | None:
    filas = query(sql, **params)
    return filas[0] if filas else None


def execute(sql: str, **params) -> int:
    cursor = _ejecutar(sql, params)
    _confirmar()
    return cursor.rowcount


@contextmanager
def transaccion():
    if g.get("en_transaccion"):
        yield
        return
    conexion = get_db()
    if not g.db_es_pg:
        conexion.execute("BEGIN IMMEDIATE")
    g.en_transaccion = True
    try:
        yield
    except BaseException:
        conexion.rollback()
        raise
    else:
        conexion.commit()
    finally:
        g.en_transaccion = False


_NOMBRE_TABLA = re.compile(r"^[a-z_]+$")


def bloquear_fila(tabla: str, fila_id: int) -> bool:
    if not _NOMBRE_TABLA.match(tabla):
        raise ValueError(f"Nombre de tabla inválido: {tabla!r}")
    if not g.get("en_transaccion"):
        raise RuntimeError("bloquear_fila sólo funciona dentro de db.transaccion().")
    bloqueo = " FOR UPDATE" if g.db_es_pg else ""
    fila = query_one(f"SELECT id FROM {tabla} WHERE id = :id{bloqueo}", id=fila_id)
    return fila is not None


def _leer_sql(nombre: str) -> str:
    with current_app.open_resource(nombre) as archivo:
        return archivo.read().decode("utf8")


# columnas y tablas agregadas después del primer deploy: se crean solas al arrancar
COLUMNAS_AGREGADAS = [
    ("reservas", "motivo", "TEXT NOT NULL DEFAULT ''"),
    ("reservas", "personas", "INTEGER CHECK (personas IS NULL OR personas > 0)"),
    ("actividades", "reserva_id", "INTEGER REFERENCES reservas (id)"),
    ("usuarios", "catedra", "INTEGER NOT NULL DEFAULT 0 CHECK (catedra IN (0, 1))"),
]

TABLAS_AGREGADAS = {
    "bloqueos": """CREATE TABLE IF NOT EXISTS bloqueos (
        id {{PK}},
        usuario_id INTEGER NOT NULL REFERENCES usuarios (id),
        admin_id INTEGER NOT NULL REFERENCES usuarios (id),
        accion TEXT NOT NULL CHECK (accion IN ('bloqueo', 'desbloqueo')),
        motivo TEXT NOT NULL,
        creado TEXT NOT NULL
    )""",
}

INDICES_AGREGADOS = [
    ("bloqueos", "CREATE INDEX IF NOT EXISTS idx_bloqueos_usuario ON bloqueos (usuario_id, creado)"),
]


def _columnas(tabla: str) -> set[str]:
    get_db()
    if g.db_es_pg:
        filas = query(
            "SELECT column_name AS nombre FROM information_schema.columns WHERE table_name = :tabla",
            tabla=tabla,
        )
        return {f["nombre"] for f in filas}
    return {f["name"] for f in query(f"PRAGMA table_info({tabla})")}


def _clave_primaria() -> str:
    get_db()
    if g.db_es_pg:
        return "INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY"
    return "INTEGER PRIMARY KEY AUTOINCREMENT"


def migrar():
    if _columnas("usuarios"):
        for tabla, definicion in TABLAS_AGREGADAS.items():
            if not _columnas(tabla):
                execute(definicion.replace("{{PK}}", _clave_primaria()))
        for tabla, indice in INDICES_AGREGADOS:
            if _columnas(tabla):
                execute(indice)
    for tabla, columna, definicion in COLUMNAS_AGREGADAS:
        existentes = _columnas(tabla)
        if existentes and columna not in existentes:
            si_falta = " IF NOT EXISTS" if g.db_es_pg else ""
            execute(f"ALTER TABLE {tabla} ADD COLUMN{si_falta} {columna} {definicion}")


def init_db(demo: bool = False):
    conexion = get_db()
    esquema = _leer_sql("schema.sql").replace("{{PK}}", _clave_primaria())
    if g.db_es_pg:
        conexion.execute(esquema)
    else:
        conexion.executescript(esquema)
    if demo:
        datos = _leer_sql("datos_demo.sql")
        if g.db_es_pg:
            conexion.execute(datos)
        else:
            conexion.executescript(datos)
    conexion.commit()


@click.command("init-db")
@click.option("--demo", is_flag=True, help="Carga datos de demostración.")
def comando_init_db(demo: bool):
    init_db(demo)
    click.echo("Base de datos inicializada." + (" Datos demo cargados." if demo else ""))


def registrar(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(comando_init_db)
    with app.app_context():
        migrar()
