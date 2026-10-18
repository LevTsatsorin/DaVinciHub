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
