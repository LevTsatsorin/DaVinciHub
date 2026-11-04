import pytest

from davincihub import db
from davincihub.reservas.datos import (
    agregar_franja_horaria,
    crear_espacio,
    deshabilitar_espacio,
    obtener_espacio,
)


def login(client, email="mica@davinci.edu.ar", password="davinci123"):
    return client.post("/auth/login", data={"email": email, "password": password})


def admin(client):
    return login(client, email="admin@davinci.edu.ar")


@pytest.fixture
def espacio(app):
    with app.app_context():
        espacio_id = crear_espacio("Sala de Pruebas", "Para tests", 12)
        agregar_franja_horaria(espacio_id, 0, "09:00", "12:00")
        return espacio_id


def test_catalogo_requiere_login(client):
    respuesta = client.get("/espacios/")
    assert respuesta.status_code == 302
    assert "/auth/login" in respuesta.headers["Location"]


def test_catalogo_muestra_activos_y_oculta_deshabilitados(client, app, espacio):
    with app.app_context():
        oculto = crear_espacio("Sala Oculta")
        deshabilitar_espacio(oculto)
    login(client)
    texto = client.get("/espacios/").get_data(as_text=True)
    assert "Sala de Pruebas" in texto
    assert "Sala Oculta" not in texto
    assert "09:00" in texto


def test_detalle_de_espacio(client, espacio):
    login(client)
    texto = client.get(f"/espacios/{espacio}").get_data(as_text=True)
    assert "Sala de Pruebas" in texto
    assert "Lunes" in texto


def test_detalle_de_espacio_deshabilitado_no_existe_para_estudiantes(client, app, espacio):
    with app.app_context():
        deshabilitar_espacio(espacio)
    login(client)
    assert client.get(f"/espacios/{espacio}").status_code == 404


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [
        ("get", "/admin/espacios/"),
        ("get", "/admin/espacios/nuevo"),
        ("post", "/admin/espacios/nuevo"),
        ("get", "/admin/espacios/{id}/editar"),
        ("post", "/admin/espacios/{id}/estado"),
    ],
)
def test_estudiante_no_entra_a_la_administracion(client, espacio, metodo, ruta):
    login(client)
    respuesta = getattr(client, metodo)(ruta.format(id=espacio))
    assert respuesta.status_code == 403


def test_admin_lista_separa_activos_y_deshabilitados(client, app, espacio):
    with app.app_context():
        apagado = crear_espacio("Sala Apagada")
        deshabilitar_espacio(apagado)
    admin(client)
    activos = client.get("/admin/espacios/").get_data(as_text=True)
    assert "Sala de Pruebas" in activos
    assert "Sala Apagada" not in activos
    assert "Deshabilitados (1)" in activos
    apagados = client.get("/admin/espacios/?estado=deshabilitados").get_data(as_text=True)
    assert "Sala Apagada" in apagados
    assert "Sala de Pruebas" not in apagados
    assert "Habilitar" in apagados


def test_deshabilitar_pide_confirmacion(client, espacio):
    admin(client)
    for ruta in ("/admin/espacios/", f"/admin/espacios/{espacio}/editar"):
        texto = client.get(ruta).get_data(as_text=True)
        assert "data-confirmar=" in texto, ruta


def test_admin_crea_espacio(client, app):
    admin(client)
    respuesta = client.post(
        "/admin/espacios/nuevo",
        data={"nombre": "Estudio de Podcast", "descripcion": "Micrófonos", "capacidad": "6"},
    )
    assert respuesta.status_code == 302
    with app.app_context():
        fila = db.query_one("SELECT * FROM espacios WHERE nombre = :n", n="Estudio de Podcast")
    assert fila["capacidad"] == 6
    assert f"/admin/espacios/{fila['id']}/editar" in respuesta.headers["Location"]


def test_admin_crea_espacio_sin_nombre_muestra_error(client):
    admin(client)
    respuesta = client.post("/admin/espacios/nuevo", data={"nombre": " ", "capacidad": "6"})
    assert respuesta.status_code == 200
    assert "El nombre del espacio es obligatorio." in respuesta.get_data(as_text=True)


def test_admin_crea_espacio_con_nombre_repetido_muestra_error(client, espacio):
    admin(client)
    respuesta = client.post("/admin/espacios/nuevo", data={"nombre": "Sala de Pruebas"})
    assert respuesta.status_code == 200
    assert "Ya existe un espacio" in respuesta.get_data(as_text=True)


def test_admin_edita_espacio(client, app, espacio):
    admin(client)
    respuesta = client.post(
        f"/admin/espacios/{espacio}/editar",
        data={"nombre": "Sala Renovada", "descripcion": "Nueva", "capacidad": "15"},
    )
    assert respuesta.status_code == 302
    with app.app_context():
        assert obtener_espacio(espacio)["nombre"] == "Sala Renovada"


def test_admin_deshabilita_y_habilita(client, app, espacio):
    admin(client)
    client.post(f"/admin/espacios/{espacio}/estado", data={"activo": "0"})
    with app.app_context():
        assert obtener_espacio(espacio)["activo"] == 0
    client.post(f"/admin/espacios/{espacio}/estado", data={"activo": "1"})
    with app.app_context():
        assert obtener_espacio(espacio)["activo"] == 1


def _formulario(nombre="Sala de Pruebas", franjas=(), **extra):
    datos = {"nombre": nombre, "descripcion": "Para tests", "capacidad": "12",
             "dia_semana": [], "abre": [], "cierra": []}
    for dia, abre, cierra in franjas:
        datos["dia_semana"].append(str(dia))
        datos["abre"].append(abre)
        datos["cierra"].append(cierra)
    datos.update(extra)
    return datos


def test_admin_guarda_datos_y_horarios_en_un_solo_envio(client, app, espacio):
    admin(client)
    respuesta = client.post(
        f"/admin/espacios/{espacio}/editar",
        data=_formulario("Sala Renovada", [(2, "14:00", "18:00"), (4, "09:00", "12:00")]),
    )
    assert respuesta.status_code == 302
    with app.app_context():
        guardado = obtener_espacio(espacio)
    assert guardado["nombre"] == "Sala Renovada"
    assert [(h["dia_semana"], h["abre"]) for h in guardado["horarios"]] == [(2, "14:00"), (4, "09:00")]


def test_admin_franjas_superpuestas_no_guarda_nada(client, app, espacio):
    admin(client)
    respuesta = client.post(
        f"/admin/espacios/{espacio}/editar",
        data=_formulario("Nombre Que No Se Guarda", [(0, "09:00", "12:00"), (0, "11:00", "13:00")]),
    )
    texto = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert "se superponen" in texto
    assert 'value="Nombre Que No Se Guarda"' in texto
    assert 'value="11:00"' in texto
    with app.app_context():
        guardado = obtener_espacio(espacio)
    assert guardado["nombre"] == "Sala de Pruebas"
    assert len(guardado["horarios"]) == 1


def test_admin_franja_incompleta_muestra_error(client, app, espacio):
    admin(client)
    respuesta = client.post(f"/admin/espacios/{espacio}/editar",
                            data=_formulario(franjas=[(1, "10:00", "")]))
    assert respuesta.status_code == 200
    assert "Completá la hora de apertura y de cierre" in respuesta.get_data(as_text=True)


def test_admin_crea_espacio_con_horarios(client, app):
    admin(client)
    respuesta = client.post("/admin/espacios/nuevo",
                            data=_formulario("Sala Nueva", [(3, "10:00", "12:00")]))
    assert respuesta.status_code == 302
    with app.app_context():
        fila = db.query_one("SELECT id FROM espacios WHERE nombre = 'Sala Nueva'")
        assert len(obtener_espacio(fila["id"])["horarios"]) == 1


def test_guardar_y_salir_va_al_destino_interno(client, espacio):
    admin(client)
    respuesta = client.post(f"/admin/espacios/{espacio}/editar",
                            data=_formulario(siguiente="/espacios/"))
    assert respuesta.headers["Location"].endswith("/espacios/")


def test_guardar_y_salir_ignora_destino_externo(client, espacio):
    admin(client)
    respuesta = client.post(f"/admin/espacios/{espacio}/editar",
                            data=_formulario(siguiente="//otro-sitio.com"))
    assert respuesta.headers["Location"].endswith(f"/admin/espacios/{espacio}/editar")


def test_formulario_avisa_cambios_sin_guardar(client, espacio):
    admin(client)
    texto = client.get(f"/admin/espacios/{espacio}/editar").get_data(as_text=True)
    assert "data-confirmar-salida" in texto


def test_barra_enlaza_al_catalogo(client):
    login(client)
    assert 'href="/espacios/"' in client.get("/").get_data(as_text=True)


def _franja(dia, abre, cierra):
    return {"dia_semana": dia, "abre": abre, "cierra": cierra}


def test_resumen_agrupa_dias_seguidos_con_el_mismo_horario():
    from davincihub.reservas.rutas import resumen_horarios

    horarios = [_franja(d, "09:00", "21:00") for d in range(5)] + [_franja(5, "10:00", "14:00")]
    assert resumen_horarios(horarios) == [("Lun–Vie", "09:00–21:00"), ("Sáb", "10:00–14:00")]


def test_resumen_dos_dias_y_dias_salteados():
    from davincihub.reservas.rutas import resumen_horarios

    horarios = [_franja(0, "10:00", "18:00"), _franja(1, "10:00", "18:00"),
                _franja(3, "10:00", "18:00")]
    assert resumen_horarios(horarios) == [("Lun, Mar y Jue", "10:00–18:00")]


def test_resumen_dias_salteados_con_el_mismo_horario_en_una_linea():
    from davincihub.reservas.rutas import resumen_horarios

    horarios = [_franja(d, "09:00", "18:00") for d in (0, 2, 4)] + [_franja(5, "10:00", "14:00")]
    assert resumen_horarios(horarios) == [("Lun, Mié y Vie", "09:00–18:00"), ("Sáb", "10:00–14:00")]


def test_resumen_tramo_largo_mas_dia_suelto():
    from davincihub.reservas.rutas import resumen_horarios

    horarios = [_franja(d, "09:00", "21:00") for d in (0, 1, 2, 3, 6)]
    assert resumen_horarios(horarios) == [("Lun–Jue y Dom", "09:00–21:00")]


def test_resumen_varias_franjas_el_mismo_dia():
    from davincihub.reservas.rutas import resumen_horarios

    horarios = [_franja(2, "09:00", "12:00"), _franja(2, "14:00", "18:00")]
    assert resumen_horarios(horarios) == [("Mié", "09:00–12:00, 14:00–18:00")]


def test_admin_ve_acceso_a_la_administracion_desde_el_catalogo(client):
    admin(client)
    assert 'href="/admin/espacios/"' in client.get("/espacios/").get_data(as_text=True)


def test_estudiante_no_ve_acceso_a_la_administracion(client):
    login(client)
    assert 'href="/admin/espacios/"' not in client.get("/espacios/").get_data(as_text=True)


@pytest.mark.parametrize(("cantidad", "texto"), [(1, "1 persona"), (30, "30 personas"),
                                                  (1500, "1.500 personas")])
def test_formato_de_personas(cantidad, texto):
    from davincihub.reservas.rutas import personas

    assert personas(cantidad) == texto


def test_catalogo_muestra_capacidad_en_singular(client, app):
    with app.app_context():
        crear_espacio("SUM", None, 1)
    login(client)
    texto = client.get("/espacios/").get_data(as_text=True)
    assert "1 persona<" in texto
    assert "1 personas" not in texto


def test_cabecera_cuenta_espacios_abiertos_hoy(client, app, monkeypatch):
    from davincihub.reservas import rutas

    with app.app_context():
        db.execute("DELETE FROM inscripciones")
        db.execute("DELETE FROM actividades")
        db.execute("DELETE FROM reservas")
        db.execute("DELETE FROM horarios_espacios")
        db.execute("DELETE FROM espacios")
        lunes = crear_espacio("Abre Lunes")
        agregar_franja_horaria(lunes, 0, "09:00", "12:00")
        martes = crear_espacio("Abre Martes")
        agregar_franja_horaria(martes, 1, "09:00", "12:00")
    monkeypatch.setattr(rutas, "dia_actual", lambda: 0)
    login(client)
    texto = client.get("/espacios/").get_data(as_text=True)
    assert "<strong>2</strong> espacios" in texto
    assert "<strong>1</strong> abierto hoy" in texto


def test_cabecera_sin_espacios_abiertos_hoy(client, app, monkeypatch):
    from davincihub.reservas import rutas

    monkeypatch.setattr(rutas, "dia_actual", lambda: 6)
    login(client)
    assert "Hoy no abre ninguno" in client.get("/espacios/").get_data(as_text=True)


def test_admin_franjas_desparejas_muestra_error_y_no_guarda(client, app, espacio):
    admin(client)
    datos = _formulario("Nombre Que No Se Guarda", [(0, "09:00", "12:00")])
    datos["dia_semana"].append("2")
    respuesta = client.post(f"/admin/espacios/{espacio}/editar", data=datos)
    assert respuesta.status_code == 200
    assert "Las franjas enviadas están incompletas" in respuesta.get_data(as_text=True)
    with app.app_context():
        assert obtener_espacio(espacio)["nombre"] == "Sala de Pruebas"
