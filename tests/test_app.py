def test_inicio_responde(client):
    respuesta = client.get("/")
    assert respuesta.status_code == 200
    assert "Da Vinci Hub" in respuesta.get_data(as_text=True)


def test_pagina_404(client):
    respuesta = client.get("/no-existe")
    assert respuesta.status_code == 404
    assert "se perdió en el espacio" in respuesta.get_data(as_text=True)


def test_pagina_403(client_rutas):
    client_rutas.post(
        "/auth/login", data={"email": "mica@davinci.edu.ar", "password": "davinci123"}
    )
    respuesta = client_rutas.get("/solo-admin")
    assert respuesta.status_code == 403
    assert "No tenés permiso" in respuesta.get_data(as_text=True)


def test_estaticos_imagenes(client):
    respuesta = client.get("/static/img/portada.png")
    assert respuesta.status_code == 200


def test_render_sin_secret_key_no_arranca(monkeypatch):
    import pytest

    from davincihub.app import create_app

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()


def test_render_cookie_segura(monkeypatch):
    from davincihub.app import create_app

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("SECRET_KEY", "x" * 32)
    aplicacion = create_app()
    assert aplicacion.config["SESSION_COOKIE_SECURE"] is True


def test_post_sin_csrf_rechazado(tmp_path):
    from davincihub import db
    from davincihub.app import create_app

    aplicacion = create_app(
        {"TESTING": True, "DATABASE_URL": f"sqlite:///{tmp_path}/c.db", "WTF_CSRF_ENABLED": True}
    )
    with aplicacion.app_context():
        db.init_db(demo=True)
    respuesta = aplicacion.test_client().post(
        "/auth/login", data={"email": "mica@davinci.edu.ar", "password": "davinci123"}
    )
    assert respuesta.status_code == 400


def test_formularios_incluyen_csrf(tmp_path):
    from davincihub import db
    from davincihub.app import create_app

    aplicacion = create_app(
        {"TESTING": True, "DATABASE_URL": f"sqlite:///{tmp_path}/c.db", "WTF_CSRF_ENABLED": True}
    )
    with aplicacion.app_context():
        db.init_db(demo=True)
    cliente = aplicacion.test_client()
    for ruta in ("/auth/login", "/auth/registro"):
        assert 'name="csrf_token"' in cliente.get(ruta).get_data(as_text=True)
