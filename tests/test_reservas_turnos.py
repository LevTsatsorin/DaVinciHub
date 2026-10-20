import pytest

from davincihub import db
from davincihub.reservas import datos, rutas


def login(client, email="mica@davinci.edu.ar"):
    return client.post("/auth/login", data={"email": email, "password": "davinci123"})


@pytest.fixture
def sala(app):
    with app.app_context():
        espacio_id = datos.crear_espacio("Sala de Turnos", capacidad=10)
        datos.reemplazar_horarios_espacio(
            espacio_id,
            [{"dia_semana": 0, "abre": "09:00", "cierra": "11:00"},
             {"dia_semana": 0, "abre": "14:00", "cierra": "15:15"},
             {"dia_semana": 2, "abre": "09:00", "cierra": "12:00"}],
        )
        return espacio_id


def _disponibilidad(app, sala, fecha):
    with app.app_context():
        return datos.obtener_disponibilidad_dia(sala, fecha)


def test_turnos_de_media_hora_por_franja(app, sala):
    bloques = rutas.turnos_del_dia(_disponibilidad(app, sala, "2030-01-07"), "2030-01-01T00:00:00")
    assert [(b["abre"], b["cierra"]) for b in bloques] == [("09:00", "11:00"), ("14:00", "15:15")]
    assert [(t["inicio"], t["fin"]) for t in bloques[0]["turnos"]] == [
        ("09:00", "09:30"), ("09:30", "10:00"), ("10:00", "10:30"), ("10:30", "11:00")]
    assert bloques[1]["turnos"][-1]["inicio"] == "15:00"
    assert bloques[1]["turnos"][-1]["fin"] == "15:15"


def test_turnos_ocupados_y_pasados(app, sala):
    with app.app_context():
        datos.crear_reserva(sala, 2, "2030-01-07T09:30", "2030-01-07T10:15")
    bloques = rutas.turnos_del_dia(_disponibilidad(app, sala, "2030-01-07"), "2030-01-07T09:10:00")
    assert [t["estado"] for t in bloques[0]["turnos"]] == ["pasado", "ocupado", "ocupado", "libre"]


def test_un_dia_anterior_queda_entero_en_el_pasado(app, sala):
    bloques = rutas.turnos_del_dia(_disponibilidad(app, sala, "2030-01-07"), "2030-01-08T08:00:00")
    assert {t["estado"] for b in bloques for t in b["turnos"]} == {"pasado"}


def test_proximos_dias_marca_los_cerrados(app, sala):
    with app.app_context():
        espacio = datos.obtener_espacio(sala)
    dias = rutas.proximos_dias("2030-01-07", espacio["horarios"], cantidad=3)
    assert [(d["fecha"], d["etiqueta"], d["numero"], d["abierto"]) for d in dias] == [
        ("2030-01-07", "Lun", "07", True), ("2030-01-08", "Mar", "08", False),
        ("2030-01-09", "Mié", "09", True)]


def test_detalle_muestra_la_grilla_y_el_panel(client, sala):
    login(client)
    texto = client.get(f"/espacios/{sala}?fecha=2030-01-07").get_data(as_text=True)
    assert 'data-inicio="09:00"' in texto
    assert 'name="motivo"' in texto
    assert 'name="personas"' in texto and 'max="10"' in texto
    assert "Confirmar reserva" in texto


def test_dia_cerrado_se_avisa_en_rojo(client, sala):
    login(client)
    texto = client.get(f"/espacios/{sala}?fecha=2030-01-08").get_data(as_text=True)
    assert 'class="aviso aviso-error"' in texto
    assert "no abre los Martes" in texto
    assert "fecha=2030-01-09" in texto


def test_reservar_guarda_motivo_y_personas(client, app, sala):
    login(client)
    respuesta = client.post(f"/espacios/{sala}/reservar", data={
        "fecha": "2030-01-07", "inicio": "09:00", "fin": "10:00",
        "motivo": "  Grupo de estudio de Álgebra ", "personas": "6"})
    assert respuesta.status_code == 302
    with app.app_context():
        fila = db.query_one("SELECT motivo, personas FROM reservas WHERE espacio_id = :e", e=sala)
    assert fila == {"motivo": "Grupo de estudio de Álgebra", "personas": 6}


@pytest.mark.parametrize(("motivo", "personas", "mensaje"), [
    ("", "4", "Contá para qué"),
    ("Ensayo", "", "cuántas personas"),
    ("Ensayo", "0", "cuántas personas"),
    ("Ensayo", "11", "capacidad"),
])
def test_reservar_exige_motivo_y_personas_validas(client, app, sala, motivo, personas, mensaje):
    login(client)
    client.post(f"/espacios/{sala}/reservar", data={
        "fecha": "2030-01-07", "inicio": "09:00", "fin": "10:00",
        "motivo": motivo, "personas": personas})
    with app.app_context():
        assert db.query_one("SELECT COUNT(*) AS n FROM reservas WHERE espacio_id = :e", e=sala)["n"] == 0
    texto = client.get(f"/espacios/{sala}?fecha=2030-01-07").get_data(as_text=True)
    assert mensaje in texto


def test_mis_reservas_muestra_motivo_y_destaca_la_nueva(client, app, sala):
    with app.app_context():
        reserva = datos.crear_reserva(sala, 2, "2030-01-07T09:00", "2030-01-07T10:00",
                                      motivo="Ensayo de la banda", personas=4)
    login(client)
    texto = client.get(f"/reservas/mis-reservas/?reserva={reserva}").get_data(as_text=True)
    assert "Ensayo de la banda" in texto
    assert "4 personas" in texto
    assert "reserva-nueva" in texto


def test_despues_de_reservar_se_confirma_una_sola_vez(client, app, sala):
    with app.app_context():
        datos.crear_reserva(sala, 2, "2030-01-07T14:00", "2030-01-07T15:00", motivo="Otra", personas=2)
    login(client)
    respuesta = client.post(f"/espacios/{sala}/reservar", follow_redirects=True, data={
        "fecha": "2030-01-07", "inicio": "09:00", "fin": "10:00",
        "motivo": "Ensayo de la banda", "personas": "4"})
    texto = respuesta.get_data(as_text=True)
    assert texto.lower().count("confirmada") == 1
    assert "Reserva confirmada" in texto
    assert "Reservar otro espacio" in texto


def test_el_formulario_pide_confirmacion_antes_de_reservar(client, sala):
    login(client)
    texto = client.get(f"/espacios/{sala}?fecha=2030-01-07").get_data(as_text=True)
    assert 'data-confirmar-tono="positivo"' in texto
    assert 'id="dialogo-confirmar"' in texto


def test_admin_de_espacios_vuelve_al_catalogo(client):
    login(client, "admin@davinci.edu.ar")
    texto = client.get("/admin/espacios/").get_data(as_text=True)
    assert 'class="enlace-volver" href="/espacios/"' in texto
