from datetime import date, timedelta

import pytest

from davincihub import db
from davincihub.actividades import datos as actividades
from davincihub.reservas import datos as reservas
from davincihub.utiles import hoy_local

ADMIN, MICA, TOMAS = 1, 2, 3


def login(client, email="mica@davinci.edu.ar"):
    return client.post("/auth/login", data={"email": email, "password": "davinci123"})


@pytest.fixture
def agenda(app):
    """Una reserva y una actividad futuras para Mica, y una propuesta pendiente de Tomás."""
    with app.app_context():
        manana = (date.fromisoformat(hoy_local()) + timedelta(days=1)).isoformat()
        sala = reservas.crear_espacio("Sala del Inicio", capacidad=30)
        reservas.reemplazar_horarios_espacio(
            sala, [{"dia_semana": d, "abre": "08:00", "cierra": "22:00"} for d in range(7)])
        reservas.crear_reserva(sala, MICA, f"{manana}T08:00", f"{manana}T09:00", motivo="Ensayo", personas=4)
        torneo = actividades.crear_actividad(TOMAS, "Torneo de ajedrez", "Partidas.", sala,
                                             f"{manana}T18:00", f"{manana}T20:00", 10, aprobada=True)
        actividades.inscribir(torneo, MICA)
        actividades.crear_actividad(TOMAS, "Club de dibujo", "Bocetos.", sala,
                                    "2030-01-09T18:00", "2030-01-09T20:00", 10)


def test_sin_sesion_invita_a_ingresar(client):
    texto = client.get("/").get_data(as_text=True)
    assert "Ingresar" in texto and "Crear cuenta" in texto
    assert "Tu agenda" not in texto


def test_con_sesion_no_aparece_ingresar(client, agenda):
    login(client)
    texto = client.get("/").get_data(as_text=True)
    assert "Ingresar" not in texto and "Crear cuenta" not in texto
    assert "Hola, Mica" in texto


def test_la_agenda_muestra_mis_reservas_y_actividades(client, agenda):
    login(client)
    texto = client.get("/").get_data(as_text=True)
    assert "Tu agenda" in texto
    assert "Sala del Inicio" in texto and "Ensayo" in texto
    assert "Torneo de ajedrez" in texto


def test_la_agenda_vacia_sugiere_que_hacer(client):
    login(client, "tomas@davinci.edu.ar")
    db_vacia = client.get("/").get_data(as_text=True)
    assert "Reservar un espacio" in db_vacia


def test_el_admin_ve_lo_que_tiene_para_revisar(client, agenda):
    login(client, "admin@davinci.edu.ar")
    texto = client.get("/").get_data(as_text=True)
    assert "Para revisar" in texto
    assert 'href="/actividades/admin?estado=pendiente"' in texto
    assert 'href="/admin/usuarios/"' in texto and 'href="/admin/carreras/"' in texto


def test_un_estudiante_no_ve_el_panel_de_admin(client, agenda):
    login(client)
    texto = client.get("/").get_data(as_text=True)
    assert "Para revisar" not in texto and 'href="/admin/carreras/"' not in texto


def test_el_pie_tiene_los_enlaces_de_la_cuenta(client, app):
    login(client)
    texto = client.get("/").get_data(as_text=True)
    pie = texto[texto.index('class="pie"'):]
    assert 'href="/reservas/mis-reservas/"' in pie and 'href="/actividades/mis-actividades"' in pie
    assert 'href="/notificaciones/"' in pie and "/admin/usuarios/" not in pie
    client.post("/auth/salir")
    login(client, "admin@davinci.edu.ar")
    texto = client.get("/").get_data(as_text=True)
    pie = texto[texto.index('class="pie"'):]
    assert 'href="/admin/usuarios/"' in pie and 'href="/admin/carreras/"' in pie


def test_el_pie_no_tiene_salir(client):
    login(client)
    texto = client.get("/").get_data(as_text=True)
    assert "Salir" not in texto[texto.index('class="pie"'):]


def test_salir_esta_dentro_del_menu_de_la_cuenta(client):
    for email in ("mica@davinci.edu.ar", "admin@davinci.edu.ar"):
        client.post("/auth/login", data={"email": email, "password": "davinci123"})
        texto = client.get("/").get_data(as_text=True)
        menu = texto[texto.index('class="menu-perfil-opciones"'):texto.index("</details>")]
        assert 'action="/auth/salir"' in menu
        cabecera = texto[:texto.index('class="menu-movil"')]
        assert cabecera.count('action="/auth/salir"') == 1
        client.post("/auth/salir")


def test_los_avisos_demo_llevan_a_una_pagina_real(client, app):
    client.post("/auth/login", data={"email": "mica@davinci.edu.ar", "password": "davinci123"})
    with app.app_context():
        avisos = db.query("SELECT id FROM notificaciones WHERE usuario_id = 2")
    for aviso in avisos:
        respuesta = client.get(f"/notificaciones/{aviso['id']}")
        assert respuesta.status_code == 302
        assert respuesta.location != "/"
        assert client.get(respuesta.location).status_code == 200


def test_inicio_del_estudiante_resume_sin_presionar_y_muestra_la_semana(client, app):
    with app.app_context():
        db.execute(
            "INSERT INTO conexiones (solicitante_id, receptor_id, estado, creado)"
            " VALUES (3, 2, 'pendiente', '2026-10-20T10:00:00')"
        )
    client.post("/auth/login", data={"email": "mica@davinci.edu.ar", "password": "davinci123"})
    texto = client.get("/").get_data(as_text=True)
    assert "<strong>1</strong>solicitud de conexión" in texto
    assert "Te están esperando" not in texto and "aceptar" not in texto
    assert "Hacer una pregunta" in texto and "Publicar un objeto" in texto
    assert "próximas dos semanas" in texto and "Tu paso por el Hub" in texto
    assert "Gente que podrías conocer" in texto
