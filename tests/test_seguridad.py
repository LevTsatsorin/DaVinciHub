import urllib.parse

import pytest
from flask import g

from davincihub import auth, db

PUBLICAS = {"inicio", "auth.login", "auth.registro", "auth.salir", "actividades.index", "actividades.detalle",
            "foro.index", "perfil.ver", "perfil.foto", "perfil.opiniones"}
SOLO_ADMIN_FUERA_DE_ADMIN = {"actividades.admin_panel", "actividades.aprobar", "actividades.rechazar",
                             "reportes.admin_cola", "reportes.resolver", "reportes.restaurar"}


def _login(client, email="mica@davinci.edu.ar", password="davinci123", url="/auth/login"):
    return client.post(url, data={"email": email, "password": password})


def _rutas(app):
    for regla in app.url_map.iter_rules():
        if regla.endpoint == "static":
            continue
        valores = {nombre: "prestamo" if nombre == "tipo" else 1 for nombre in regla.arguments}
        for metodo in sorted(regla.methods - {"HEAD", "OPTIONS"}):
            yield regla, regla.build(valores)[1], metodo


def test_volver_a_la_pagina_que_se_queria_abrir(client):
    respuesta = client.get("/estudiantes/buscar?comision=DM")
    assert respuesta.status_code == 302
    destino = respuesta.headers["Location"]
    assert destino.startswith("/auth/login?siguiente=")
    respuesta = _login(client, url=destino)
    assert respuesta.headers["Location"] == "/estudiantes/buscar?comision=DM"


@pytest.mark.parametrize("siguiente", [
    "https://evil.example.com/", "//evil.example.com", "/\\evil.example.com", "\\\\evil.example.com",
    "/\t/evil.example.com", "https:evil.example.com", "javascript:alert(1)", "evil.example.com", "",
])
def test_login_nunca_lleva_a_otro_sitio(client, siguiente):
    respuesta = _login(client, url="/auth/login?" + urllib.parse.urlencode({"siguiente": siguiente}))
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/"


def test_login_trabaja_igual_exista_o_no_el_email(client, monkeypatch):
    llamadas = []
    original = auth.check_password_hash

    def contar(hash_guardado, password):
        llamadas.append(hash_guardado)
        return original(hash_guardado, password)

    monkeypatch.setattr(auth, "check_password_hash", contar)
    inexistente = _login(client, email="nadie@davinci.edu.ar", password="davinci124").get_data(as_text=True)
    incorrecta = _login(client, password="davinci124").get_data(as_text=True)
    assert len(llamadas) == 2
    assert llamadas[0].split("$")[0] == llamadas[1].split("$")[0]
    assert "Email o contraseña incorrectos." in inexistente and "Email o contraseña incorrectos." in incorrecta


def test_el_hash_de_la_contrasena_no_llega_a_las_plantillas(app, client):
    _login(client)
    with client:
        client.get("/")
        assert g.usuario["email"] == "mica@davinci.edu.ar"
        assert "password_hash" not in g.usuario


def test_cambiar_contrasena_sigue_funcionando(client):
    _login(client)
    client.post("/estudiantes/2/contrasena",
                data={"password_actual": "davinci123", "password_nueva": "otra-clave-1", "confirmar": "otra-clave-1"})
    client.post("/auth/salir")
    assert _login(client, password="otra-clave-1").headers["Location"] == "/"


def test_cada_ruta_privada_pide_iniciar_sesion(app, client):
    for regla, url, metodo in _rutas(app):
        if regla.endpoint in PUBLICAS:
            continue
        respuesta = client.open(url, method=metodo)
        assert respuesta.status_code == 302, (metodo, url)
        assert respuesta.headers["Location"].startswith("/auth/login"), (metodo, url)


def test_las_rutas_de_administracion_rechazan_a_estudiantes(app, client):
    _login(client)
    for regla, url, metodo in _rutas(app):
        if regla.rule.startswith("/admin/") or regla.endpoint in SOLO_ADMIN_FUERA_DE_ADMIN:
            assert client.open(url, method=metodo).status_code == 403, (metodo, url)


def test_reiniciar_una_base_con_datos_pide_confirmacion(app):
    corredor = app.test_cli_runner()
    resultado = corredor.invoke(args=["init-db"], input="no\n")
    assert resultado.exit_code != 0
    assert "se borra" in resultado.output
    with app.app_context():
        assert db.query_one("SELECT count(*) AS n FROM usuarios")["n"] > 0
    assert corredor.invoke(args=["init-db"], input="borrar\n").exit_code == 0
    with app.app_context():
        assert db.query_one("SELECT count(*) AS n FROM usuarios")["n"] == 0


def test_reiniciar_con_si_no_pregunta(app):
    resultado = app.test_cli_runner().invoke(args=["init-db", "--demo", "--si"])
    assert resultado.exit_code == 0 and "se borra" not in resultado.output


def test_una_base_vacia_se_inicializa_sin_preguntar(tmp_path):
    from davincihub.app import create_app

    aplicacion = create_app({"TESTING": True, "DATABASE_URL": f"sqlite:///{tmp_path}/vacia.db"})
    resultado = aplicacion.test_cli_runner().invoke(args=["init-db", "--demo"])
    assert resultado.exit_code == 0 and "se borra" not in resultado.output


def test_una_accion_sin_sesion_no_se_guarda_como_destino(client):
    respuesta = client.post("/actividades/1/inscribir")
    assert respuesta.headers["Location"] == "/auth/login"
