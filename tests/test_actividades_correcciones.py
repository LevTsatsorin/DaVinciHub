import pytest

from davincihub import db
from davincihub.actividades import datos


def login(client, email="mica@davinci.edu.ar"):
    return client.post("/auth/login", data={"email": email, "password": "davinci123"})


@pytest.fixture
def martes_14_00(monkeypatch):
    monkeypatch.setattr(datos, "ahora_local", lambda: "2026-10-20T14:00:00")


def _crear(**cambios):
    campos = {"creador_id": 2, "nombre": "Grupo de estudio", "descripcion": "Repaso para el parcial.",
              "inicio": "2030-01-07T10:00", "ubicacion": "Aula 3", "cupo_maximo": 10}
    return datos.crear_actividad(**(campos | cambios))


def test_actividad_dentro_de_una_hora_no_es_pasado(app, martes_14_00):
    with app.app_context():
        assert _crear(inicio="2026-10-20T15:00") > 0


def test_actividad_anterior_a_la_hora_local_es_pasado(app, martes_14_00):
    with app.app_context(), pytest.raises(datos.ErrorActividad, match="pasadas"):
        _crear(inicio="2026-10-20T13:30")


def test_inicio_con_zona_se_guarda_en_hora_local(app):
    with app.app_context():
        actividad = datos.obtener_actividad(_crear(inicio="2030-01-07T13:00+00:00"))
    assert actividad["inicio"] == "2030-01-07T10:00:00"


def test_nombre_demasiado_largo_se_rechaza(app):
    with app.app_context(), pytest.raises(datos.ErrorActividad, match="nombre"):
        _crear(nombre="x" * (datos.LIMITE_NOMBRE + 1))


def test_cupo_no_numerico_se_avisa_en_el_formulario(client, app):
    login(client)
    respuesta = client.post("/actividades/crear", data={
        "nombre": "Torneo", "descripcion": "Torneo de ajedrez", "inicio": "2030-01-07T10:00",
        "ubicacion": "Aula 3", "cupo_maximo": "veinte"})
    assert respuesta.status_code == 200
    assert "número entero" in respuesta.get_data(as_text=True)
    with app.app_context():
        assert db.query_one("SELECT COUNT(*) AS n FROM actividades WHERE nombre = 'Torneo'")["n"] == 0


def test_listado_publico_no_muestra_actividades_terminadas(app, martes_14_00):
    with app.app_context():
        vieja = _crear(inicio="2026-10-21T10:00")
        nueva = _crear(inicio="2026-10-22T10:00")
        datos.aprobar_actividad(vieja)
        datos.aprobar_actividad(nueva)
        db.execute("UPDATE actividades SET inicio = '2026-10-19T10:00:00' WHERE id = :id", id=vieja)
        ids = [a["id"] for a in datos.listar_actividades_publicas()]
    assert nueva in ids and vieja not in ids


def test_si_falla_el_aviso_la_actividad_sigue_pendiente(app, monkeypatch):
    def aviso_roto(*args, **kwargs):
        raise RuntimeError("sin avisos")

    with app.app_context():
        actividad = _crear()
        monkeypatch.setattr(datos, "notificar", aviso_roto)
        with pytest.raises(RuntimeError):
            datos.aprobar_actividad(actividad)
        assert datos.obtener_actividad(actividad)["estado"] == "pendiente"


def test_moderar_dos_veces_se_avisa_como_error(client, app):
    with app.app_context():
        actividad = _crear()
        datos.aprobar_actividad(actividad)
    login(client, "admin@davinci.edu.ar")
    texto = client.post(f"/actividades/admin/{actividad}/aprobar", follow_redirects=True).get_data(as_text=True)
    assert 'class="aviso aviso-error"' in texto
