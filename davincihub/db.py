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


def _a_psycopg(sql: str) -> str:
    sql = sql.replace("%", "%%")
    return re.sub(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)", r"%(\1)s", sql)


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


def _leer_sql(nombre: str) -> str:
    with current_app.open_resource(nombre) as archivo:
        return archivo.read().decode("utf8")


def init_db(demo: bool = False):
    conexion = get_db()
    pk = (
        "INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY"
        if g.db_es_pg
        else "INTEGER PRIMARY KEY AUTOINCREMENT"
    )
    esquema = _leer_sql("schema.sql").replace("{{PK}}", pk)
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
