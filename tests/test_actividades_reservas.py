import pytest

from davincihub import db
from davincihub.actividades import datos
from davincihub.reservas import datos as reservas


def login(client, email="mica@davinci.edu.ar"):
    return client.post("/auth/login", data={"email": email, "password": "davinci123"})


@pytest.fixture
def sala(app):
    with app.app_context():
        espacio_id = reservas.crear_espacio("Sala de Eventos", capacidad=40)
        reservas.reemplazar_horarios_espacio(espacio_id, [{"dia_semana": 0, "abre": "09:00", "cierra": "21:00"}])
        return espacio_id


def _proponer(sala, **cambios):
    campos = {"creador_id": 2, "nombre": "Torneo de ajedrez", "descripcion": "Partidas rápidas.",
              "espacio_id": sala, "inicio": "2030-01-07T18:00", "fin": "2030-01-07T20:00", "cupo_maximo": 16}
    return datos.crear_actividad(**(campos | cambios))


def _reserva_de(actividad_id):
    return db.query_one(
        "SELECT r.* FROM reservas r JOIN actividades a ON a.reserva_id = r.id WHERE a.id = :id", id=actividad_id)


def test_proponer_reserva_el_espacio(app, sala):
    with app.app_context():
        actividad = _proponer(sala)
        reserva = _reserva_de(actividad)
        guardada = datos.obtener_actividad(actividad)
    assert reserva["espacio_id"] == sala and reserva["estado"] == "confirmada"
    assert (reserva["inicio"], reserva["fin"]) == ("2030-01-07T18:00:00", "2030-01-07T20:00:00")
    assert (reserva["motivo"], reserva["personas"]) == ("Torneo de ajedrez", 16)
    assert guardada["ubicacion"] == "Sala de Eventos"


def test_no_se_propone_sobre_un_horario_reservado(app, sala):
    with app.app_context():
        reservas.crear_reserva(sala, 3, "2030-01-07T19:00", "2030-01-07T19:30")
        with pytest.raises(datos.ErrorActividad, match="reservado"):
            _proponer(sala)
        assert db.query_one("SELECT COUNT(*) AS n FROM actividades WHERE nombre = 'Torneo de ajedrez'")["n"] == 0


def test_no_se_propone_fuera_del_horario_del_espacio(app, sala):
    with app.app_context(), pytest.raises(datos.ErrorActividad):
        _proponer(sala, inicio="2030-01-07T20:00", fin="2030-01-07T22:00")


def test_el_fin_es_obligatorio(app, sala):
    with app.app_context(), pytest.raises(datos.ErrorActividad, match="termina"):
        _proponer(sala, fin="")


def test_rechazar_libera_el_horario(app, sala):
    with app.app_context():
        actividad = _proponer(sala)
        datos.rechazar_actividad(actividad, "Ese día hay exámenes.")
        assert _reserva_de(actividad)["estado"] == "cancelada"
        assert reservas.crear_reserva(sala, 3, "2030-01-07T18:00", "2030-01-07T20:00") > 0


def test_aprobar_mantiene_la_reserva(app, sala):
    with app.app_context():
        actividad = _proponer(sala)
        datos.aprobar_actividad(actividad)
        assert _reserva_de(actividad)["estado"] == "confirmada"


def test_la_reserva_de_una_actividad_no_se_cancela_desde_mis_reservas(app, sala):
    with app.app_context():
        reserva = _reserva_de(_proponer(sala))
        with pytest.raises(reservas.ErrorReserva, match="actividad"):
            reservas.cancelar_reserva(reserva["id"], usuario_id=2)


def test_proponer_no_avisa_una_reserva_suelta(app, sala):
    with app.app_context():
        antes = db.query_one("SELECT COUNT(*) AS n FROM notificaciones WHERE usuario_id = 2")["n"]
        _proponer(sala)
        assert db.query_one("SELECT COUNT(*) AS n FROM notificaciones WHERE usuario_id = 2")["n"] == antes


def test_el_formulario_muestra_la_linea_de_tiempo_del_espacio(client, sala):
    login(client)
    texto = client.get(f"/actividades/crear?espacio={sala}&fecha=2030-01-07").get_data(as_text=True)
    assert 'data-inicio="09:00"' in texto
    assert "data-panel-reserva" in texto
    assert 'name="nombre"' in texto


def test_proponer_desde_la_web(client, app, sala):
    login(client)
    respuesta = client.post("/actividades/crear", data={
        "espacio_id": sala, "fecha": "2030-01-07", "inicio": "18:00", "fin": "20:00",
        "nombre": "Torneo de ajedrez", "descripcion": "Partidas rápidas.", "cupo_maximo": "16"})
    assert respuesta.status_code == 302
    with app.app_context():
        actividad = db.query_one("SELECT id FROM actividades WHERE nombre = 'Torneo de ajedrez'")
        assert _reserva_de(actividad["id"])["espacio_id"] == sala


def test_mis_reservas_marca_la_reserva_de_la_actividad(client, app, sala):
    with app.app_context():
        _proponer(sala)
    login(client)
    texto = client.get("/reservas/mis-reservas/").get_data(as_text=True)
    assert "Actividad en revisión" in texto and "Cancelar reserva" not in texto


def test_la_actividad_del_admin_se_publica_sin_moderacion(client, app, sala):
    login(client, "admin@davinci.edu.ar")
    client.post("/actividades/crear", data={
        "espacio_id": sala, "fecha": "2030-01-07", "inicio": "18:00", "fin": "20:00",
        "nombre": "Charla de bienvenida", "descripcion": "Para ingresantes.", "cupo_maximo": "30"})
    with app.app_context():
        actividad = db.query_one("SELECT id, estado FROM actividades WHERE nombre = 'Charla de bienvenida'")
        assert actividad["estado"] == "aprobada"
        assert _reserva_de(actividad["id"])["estado"] == "confirmada"


def test_la_cabecera_no_muestra_cifras_sueltas(client):
    login(client)
    texto = client.get("/actividades/").get_data(as_text=True)
    assert "esta semana" not in texto


def test_el_detalle_muestra_lugar_duracion_y_otras(client, app, sala):
    with app.app_context():
        db.execute("DELETE FROM inscripciones")
        db.execute("DELETE FROM actividades")
        una = _proponer(sala)
        otra = _proponer(sala, nombre="Club de lectura", inicio="2030-01-07T10:00", fin="2030-01-07T11:30")
        datos.aprobar_actividad(una)
        datos.aprobar_actividad(otra)
    login(client)
    texto = client.get(f"/actividades/{una}").get_data(as_text=True)
    assert f"/espacios/{sala}?fecha=2030-01-07" in texto
    assert "2 h" in texto
    assert "Otras actividades" in texto and "Club de lectura" in texto


@pytest.mark.parametrize("cupo", ["3000000000", "2147483648"])
def test_un_cupo_enorme_se_rechaza_con_un_mensaje(client, app, cupo):
    with app.app_context():
        sin_capacidad = reservas.crear_espacio("Patio")
        reservas.reemplazar_horarios_espacio(sin_capacidad, [{"dia_semana": 0, "abre": "09:00", "cierra": "21:00"}])
    login(client)
    texto = client.post("/actividades/crear", follow_redirects=True, data={
        "espacio_id": sin_capacidad, "fecha": "2030-01-07", "inicio": "18:00", "fin": "20:00",
        "nombre": "Recital", "descripcion": "Bandas del instituto.", "cupo_maximo": cupo}).get_data(as_text=True)
    assert "cupo" in texto.lower() and 'class="aviso aviso-error"' in texto
    with app.app_context():
        assert db.query_one("SELECT COUNT(*) AS n FROM actividades WHERE nombre = 'Recital'")["n"] == 0


def test_cupo_mayor_a_la_capacidad_habla_de_cupo(app, sala):
    with app.app_context(), pytest.raises(datos.ErrorActividad, match="cupo"):
        _proponer(sala, cupo_maximo=41)
