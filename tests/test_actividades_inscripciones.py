from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from davincihub import db
from davincihub.actividades import datos
from davincihub.reservas import datos as reservas

MICA, TOMAS, LUCIA = 2, 3, 4


def login(client, email="mica@davinci.edu.ar"):
    return client.post("/auth/login", data={"email": email, "password": "davinci123"})


@pytest.fixture
def actividad(app):
    """Actividad aprobada de Tomás con cupo 1."""
    with app.app_context():
        sala = reservas.crear_espacio("Sala de Inscripciones", capacidad=30)
        reservas.reemplazar_horarios_espacio(
            sala, [{"dia_semana": d, "abre": "08:00", "cierra": "22:00"} for d in range(7)])
        actividad_id = datos.crear_actividad(TOMAS, "Torneo de ajedrez", "Partidas rápidas.", sala,
                                             "2030-01-07T18:00", "2030-01-07T20:00", 1)
        datos.aprobar_actividad(actividad_id)
        return actividad_id


def _avisos(usuario_id, enlace):
    return db.query("SELECT cuerpo FROM notificaciones WHERE usuario_id = :u AND enlace = :e",
                    u=usuario_id, e=enlace)


def test_inscripciones_simultaneas_al_ultimo_lugar_solo_acepta_una(app, actividad):
    largada = Barrier(2)

    def intentar(usuario_id):
        with app.app_context():
            largada.wait()
            try:
                datos.inscribir(actividad, usuario_id)
                return True
            except datos.ErrorActividad:
                return False

    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        resultados = list(ejecutor.map(intentar, [MICA, LUCIA]))

    assert sum(resultados) == 1
    with app.app_context():
        assert datos.obtener_actividad(actividad)["inscriptos"] == 1
        assert len(_avisos(TOMAS, f"/actividades/{actividad}/inscriptos")) == 1


def test_dar_de_baja_libera_el_cupo(app, actividad):
    with app.app_context():
        datos.inscribir(actividad, MICA)
        datos.dar_de_baja(actividad, MICA)
        assert not datos.esta_inscripto(actividad, MICA)
        datos.inscribir(actividad, LUCIA)
        assert datos.obtener_actividad(actividad)["inscriptos"] == 1


def test_actividad_completa_no_acepta_mas_y_lo_muestra(client, app, actividad):
    with app.app_context():
        datos.inscribir(actividad, MICA)
        with pytest.raises(datos.ErrorActividad, match="completa"):
            datos.inscribir(actividad, LUCIA)
    login(client, "lucia@davinci.edu.ar")
    texto = client.get(f"/actividades/{actividad}").get_data(as_text=True)
    assert "Actividad completa" in texto
    assert "Inscribirme" not in texto


@pytest.mark.parametrize(("usuario", "preparar", "mensaje"), [
    (TOMAS, None, "propia"),
    (MICA, "doble", "Ya estás inscripto"),
    (MICA, "pendiente", "aprobadas"),
    (MICA, "pasada", "ya empezó"),
])
def test_reglas_de_inscripcion(app, actividad, usuario, preparar, mensaje):
    with app.app_context():
        if preparar == "doble":
            db.execute("UPDATE actividades SET cupo_maximo = 5 WHERE id = :id", id=actividad)
            datos.inscribir(actividad, MICA)
        elif preparar == "pendiente":
            db.execute("UPDATE actividades SET estado = 'pendiente' WHERE id = :id", id=actividad)
        elif preparar == "pasada":
            db.execute("UPDATE actividades SET inicio = '2020-01-06T18:00:00', fin = '2030-01-07T20:00:00'"
                       " WHERE id = :id", id=actividad)
        with pytest.raises(datos.ErrorActividad, match=mensaje):
            datos.inscribir(actividad, usuario)


def test_cancelar_avisa_a_los_inscriptos_y_libera_el_espacio(app, actividad):
    with app.app_context():
        datos.inscribir(actividad, MICA)
        datos.cancelar_actividad(actividad, TOMAS)
        assert datos.obtener_actividad(actividad)["estado"] == "cancelada"
        assert "cancelada" in _avisos(MICA, f"/actividades/{actividad}")[0]["cuerpo"]
        reserva = db.query_one("SELECT r.estado FROM reservas r JOIN actividades a ON a.reserva_id = r.id"
                               " WHERE a.id = :id", id=actividad)
        assert reserva["estado"] == "cancelada"


def test_solo_el_creador_o_un_admin_cancela(app, actividad):
    with app.app_context(), pytest.raises(datos.ErrorActividad, match="creador"):
        datos.cancelar_actividad(actividad, MICA)


def test_inscribirse_y_darse_de_baja_desde_la_web(client, app, actividad):
    login(client)
    texto = client.get(f"/actividades/{actividad}").get_data(as_text=True)
    assert "Inscribirme" in texto
    client.post(f"/actividades/{actividad}/inscribir")
    texto = client.get(f"/actividades/{actividad}").get_data(as_text=True)
    assert "Estás inscripto" in texto and "Darme de baja" in texto
    client.post(f"/actividades/{actividad}/baja")
    with app.app_context():
        assert not datos.esta_inscripto(actividad, MICA)


def test_el_creador_ve_la_lista_de_inscriptos(client, app, actividad):
    with app.app_context():
        datos.inscribir(actividad, MICA)
    login(client, "tomas@davinci.edu.ar")
    texto = client.get(f"/actividades/{actividad}/inscriptos").get_data(as_text=True)
    assert "Mica Suárez" in texto


def test_otro_estudiante_no_ve_los_inscriptos(client, actividad):
    login(client, "lucia@davinci.edu.ar")
    assert client.get(f"/actividades/{actividad}/inscriptos").status_code == 404


def test_mis_actividades_muestra_mis_inscripciones(client, app, actividad):
    with app.app_context():
        datos.inscribir(actividad, MICA)
    login(client)
    texto = client.get("/actividades/mis-actividades").get_data(as_text=True)
    assert "Me inscribí" in texto and "Torneo de ajedrez" in texto


def test_la_lista_marca_las_actividades_completas(client, app, actividad):
    with app.app_context():
        datos.inscribir(actividad, MICA)
    login(client, "lucia@davinci.edu.ar")
    texto = client.get("/actividades/?mes=2030-01").get_data(as_text=True)
    assert "Completa" in texto


def test_el_organizador_y_los_inscriptos_enlazan_a_su_perfil(client, app, actividad):
    with app.app_context():
        datos.inscribir(actividad, MICA)
    login(client, "tomas@davinci.edu.ar")
    assert f'href="/estudiantes/{TOMAS}"' in client.get(f"/actividades/{actividad}").get_data(as_text=True)
    assert f'href="/estudiantes/{MICA}"' in client.get(f"/actividades/{actividad}/inscriptos").get_data(as_text=True)


def test_un_admin_organizador_no_enlaza_a_un_perfil(client, app):
    login(client, "admin@davinci.edu.ar")
    with app.app_context():
        sala = reservas.crear_espacio("Sala Admin", capacidad=30)
        reservas.reemplazar_horarios_espacio(sala, [{"dia_semana": 0, "abre": "08:00", "cierra": "22:00"}])
        actividad = datos.crear_actividad(1, "Charla institucional", "Bienvenida.", sala,
                                          "2030-01-07T10:00", "2030-01-07T11:00", 20, aprobada=True)
    assert 'href="/estudiantes/1"' not in client.get(f"/actividades/{actividad}").get_data(as_text=True)


def test_si_cancela_un_admin_se_avisa_al_creador(app, actividad):
    with app.app_context():
        datos.cancelar_actividad(actividad, 1)
        avisos = [a for a in _avisos(TOMAS, f"/actividades/{actividad}") if "cancel" in a["cuerpo"]]
    assert len(avisos) == 1


def test_si_cancela_el_creador_no_se_avisa_a_si_mismo(app, actividad):
    with app.app_context():
        datos.cancelar_actividad(actividad, TOMAS)
        assert not [a for a in _avisos(TOMAS, f"/actividades/{actividad}") if "cancel" in a["cuerpo"]]


def test_la_baja_avisa_al_creador(app, actividad):
    with app.app_context():
        datos.inscribir(actividad, MICA)
        datos.dar_de_baja(actividad, MICA)
        avisos = _avisos(TOMAS, f"/actividades/{actividad}/inscriptos")
    assert len(avisos) == 2 and "baja" in avisos[1]["cuerpo"]
