import pytest

from davincihub import db
from davincihub.reservas import datos, rutas


def login(client, email="mica@davinci.edu.ar"):
    return client.post("/auth/login", data={"email": email, "password": "davinci123"})


@pytest.fixture
def salas(app):
    with app.app_context():
        db.execute("DELETE FROM actividades")
        db.execute("DELETE FROM reservas")
        db.execute("DELETE FROM horarios_espacios")
        db.execute("DELETE FROM espacios")
        grande = datos.crear_espacio("Sala Grande", capacidad=40)
        datos.reemplazar_horarios_espacio(grande, [{"dia_semana": 0, "abre": "09:00", "cierra": "13:00"}])
        chica = datos.crear_espacio("Estudio Chico", capacidad=4)
        datos.reemplazar_horarios_espacio(chica, [{"dia_semana": 0, "abre": "10:00", "cierra": "12:00"}])
        martes = datos.crear_espacio("Aula de los Martes", capacidad=20)
        datos.reemplazar_horarios_espacio(martes, [{"dia_semana": 1, "abre": "09:00", "cierra": "12:00"}])
        datos.crear_reserva(grande, 2, "2030-01-07T10:00", "2030-01-07T11:00")
        return {"grande": grande, "chica": chica, "martes": martes}


def test_rangos_libres_une_turnos_seguidos(app, salas):
    with app.app_context():
        disponibilidad = datos.obtener_disponibilidad_dia(salas["grande"], "2030-01-07")
    bloques = rutas.turnos_del_dia(disponibilidad, "2030-01-01T00:00:00")
    assert rutas.rangos_libres(bloques) == [("09:00", "10:00"), ("11:00", "13:00")]


def test_filtrar_por_personas_oculta_los_chicos(client, salas):
    login(client)
    texto = client.get("/espacios/?personas=10").get_data(as_text=True)
    assert "Sala Grande" in texto and "Aula de los Martes" in texto
    assert "Estudio Chico" not in texto


def test_filtrar_por_dia_muestra_los_huecos_libres(client, salas):
    login(client)
    texto = client.get("/espacios/?fecha=2030-01-07").get_data(as_text=True)
    assert "09:00–10:00" in texto and "11:00–13:00" in texto
    assert "Sala Grande" in texto and "Aula de los Martes" not in texto
    assert f"/espacios/{salas['grande']}?fecha=2030-01-07" in texto


def test_buscar_por_nombre(client, salas):
    login(client)
    texto = client.get("/espacios/?q=estudio").get_data(as_text=True)
    assert "Estudio Chico" in texto and "Sala Grande" not in texto


def test_filtros_invalidos_no_rompen(client, salas):
    login(client)
    assert client.get("/espacios/?fecha=2030-02-31&personas=muchas").status_code == 200
