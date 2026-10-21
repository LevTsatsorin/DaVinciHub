import pytest

from davincihub import db
from davincihub.actividades import datos, semanas_del_mes
from davincihub.reservas import datos as reservas


def login(client, email="mica@davinci.edu.ar"):
    return client.post("/auth/login", data={"email": email, "password": "davinci123"})


@pytest.fixture
def doce_en_enero(app):
    with app.app_context():
        db.execute("DELETE FROM inscripciones")
        db.execute("DELETE FROM actividades")
        sala = reservas.crear_espacio("Sala Calendario", capacidad=50)
        reservas.reemplazar_horarios_espacio(
            sala, [{"dia_semana": d, "abre": "08:00", "cierra": "22:00"} for d in range(7)])
        ids = []
        for dia in range(5, 17):
            actividad = datos.crear_actividad(2, f"Encuentro {dia:02d}", "Charla abierta.", sala,
                                              f"2030-01-{dia:02d}T18:00", f"2030-01-{dia:02d}T19:00", 20)
            datos.aprobar_actividad(actividad)
            ids.append(actividad)
        return ids


def test_semanas_del_mes_empiezan_en_lunes():
    semanas = semanas_del_mes(2026, 11, {"2026-11-12": 2}, "2026-10-20")
    assert semanas[0][0]["fecha"] == "2026-10-26" and semanas[-1][-1]["fecha"] == "2026-12-06"
    dia = next(c for s in semanas for c in s if c["fecha"] == "2026-11-12")
    assert dia["cantidad"] == 2 and dia["en_mes"]
    assert not semanas[0][0]["en_mes"]


def test_calendario_marca_los_dias_con_actividades(client, doce_en_enero):
    login(client)
    texto = client.get("/actividades/?mes=2030-01").get_data(as_text=True)
    assert "Enero 2030" in texto
    assert texto.count("dia-con-actividad") == 12


def test_la_lista_se_pagina_de_a_diez(client, doce_en_enero):
    login(client)
    primera = client.get("/actividades/?mes=2030-01").get_data(as_text=True)
    segunda = client.get("/actividades/?mes=2030-01&pagina=2").get_data(as_text=True)
    assert primera.count('class="actividad-fila"') == 10
    assert segunda.count('class="actividad-fila"') == 1
    assert "Página 2 de 2" in segunda


def test_elegir_un_dia_filtra_la_lista(client, doce_en_enero):
    login(client)
    texto = client.get("/actividades/?mes=2030-01&dia=2030-01-09").get_data(as_text=True)
    assert texto.count('class="actividad-fila"') == 1
    assert "Encuentro 09" in texto


def test_un_mes_invalido_no_rompe_la_pagina(client):
    login(client)
    assert client.get("/actividades/?mes=2030-13&pagina=abc").status_code == 200


@pytest.mark.parametrize("consulta", [
    "mes=2026-11&dia=2026-11-99", "mes=2026-02&dia=2026-02-30", "mes=2026-11&dia=2026-11-1x",
    "dia=2026-02-30", "mes=9999-12", "mes=0001-01", "mes=9999-12&dia=9999-12-31"])
def test_parametros_raros_no_rompen_el_listado(client, consulta):
    login(client)
    assert client.get(f"/actividades/?{consulta}").status_code == 200


def test_el_calendario_no_cuenta_actividades_terminadas(client, app, monkeypatch, doce_en_enero):
    monkeypatch.setattr(datos, "ahora_local", lambda: "2030-01-10T12:00:00")
    login(client)
    texto = client.get("/actividades/?mes=2030-01").get_data(as_text=True)
    assert texto.count("dia-con-actividad") == 7
