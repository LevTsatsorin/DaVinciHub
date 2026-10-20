from datetime import date, timedelta

from davincihub import db
from davincihub.reservas import datos


def preparar_espacio(app):
    with app.app_context():
        espacio_id = datos.crear_espacio(
            nombre="Espacio web D2",
            descripcion="Espacio para probar reservas desde la web.",
            capacidad=12,
        )
        for dia in range(7):
            datos.agregar_franja_horaria(espacio_id, dia, "08:00", "18:00")
        usuario = db.query_one("SELECT id FROM usuarios WHERE email = :email", email="mica@davinci.edu.ar")
        admin = db.query_one("SELECT id FROM usuarios WHERE email = :email", email="admin@davinci.edu.ar")
    return espacio_id, usuario["id"], admin["id"], (date.today() + timedelta(days=7)).isoformat()


def iniciar_sesion(client, email="mica@davinci.edu.ar"):
    respuesta = client.post("/auth/login", data={"email": email, "password": "davinci123"})
    assert respuesta.status_code == 302


def test_catalogo_y_detalle_muestran_disponibilidad(app, client):
    espacio_id, usuario_id, _, fecha = preparar_espacio(app)
    with app.app_context():
        datos.crear_reserva(
            espacio_id, usuario_id, f"{fecha}T10:00", f"{fecha}T12:00"
        )

    iniciar_sesion(client)
    catalogo = client.get("/espacios/")
    detalle = client.get(f"/espacios/{espacio_id}?fecha={fecha}")

    assert catalogo.status_code == 200
    assert "Espacio web D2" in catalogo.get_data(as_text=True)
    assert detalle.status_code == 200
    contenido = detalle.get_data(as_text=True)
    assert "Libre" in contenido
    assert "Ocupado" in contenido
    assert "08:00" in contenido
    assert "10:00" in contenido
    assert "12:00" in contenido


def test_reservar_ver_mis_reservas_y_cancelar_desde_la_web(app, client):
    espacio_id, _, _, fecha = preparar_espacio(app)
    iniciar_sesion(client)

    respuesta = client.post(
        f"/espacios/{espacio_id}/reservar",
        data={"fecha": fecha, "inicio": "10:00", "fin": "12:00"},
    )
    assert respuesta.status_code == 302
    assert "/reservas/mis-reservas/" in respuesta.headers["Location"]

    with app.app_context():
        reserva = db.query_one(
            "SELECT id, estado FROM reservas WHERE espacio_id = :espacio_id",
            espacio_id=espacio_id,
        )
    assert reserva["estado"] == "confirmada"

    mis_reservas = client.get("/reservas/mis-reservas/")
    assert mis_reservas.status_code == 200
    assert "Espacio web D2" in mis_reservas.get_data(as_text=True)

    cancelar = client.post(f"/reservas/{reserva['id']}/cancelar")
    assert cancelar.status_code == 302
    with app.app_context():
        assert datos.obtener_reserva(reserva["id"])["estado"] == "cancelada"


def test_admin_ve_reservas_del_espacio(client, app):
    espacio_id, usuario_id, _, fecha = preparar_espacio(app)
    with app.app_context():
        datos.crear_reserva(
            espacio_id, usuario_id, f"{fecha}T10:00", f"{fecha}T12:00"
        )

    iniciar_sesion(client, email="admin@davinci.edu.ar")
    respuesta = client.get(f"/admin/espacios/{espacio_id}/reservas/")

    assert respuesta.status_code == 200
    contenido = respuesta.get_data(as_text=True)
    assert "Mica" in contenido
    assert "mica@davinci.edu.ar" in contenido
    assert "Confirmada" in contenido


def test_admin_accede_a_todas_las_reservas_desde_el_catalogo(client, app):
    espacio_id, usuario_id, _, fecha = preparar_espacio(app)
    with app.app_context():
        datos.crear_reserva(
            espacio_id, usuario_id, f"{fecha}T10:00", f"{fecha}T12:00"
        )
        datos.crear_espacio(nombre="Espacio sin reservas", activo=0)

    iniciar_sesion(client, email="admin@davinci.edu.ar")
    catalogo = client.get("/espacios/")
    todas = client.get("/admin/reservas/")

    assert "Todas las reservas" in catalogo.get_data(as_text=True)
    assert todas.status_code == 200
    contenido = todas.get_data(as_text=True)
    assert "Espacio web D2" in contenido
    assert "mica@davinci.edu.ar" in contenido
    assert "Espacio sin reservas" in contenido
    assert "Deshabilitado" in contenido


def test_no_admin_no_puede_ver_reservas_admin(client, app):
    espacio_id, _, _, _ = preparar_espacio(app)
    iniciar_sesion(client)

    assert client.get(f"/admin/espacios/{espacio_id}/reservas/").status_code == 403
    assert client.get("/admin/reservas/").status_code == 403


def test_resumen_agrupa_dias_seguidos_con_el_mismo_horario():
    horarios = [
        {"dia_semana": dia, "abre": "09:00", "cierra": "21:00"} for dia in range(5)
    ] + [{"dia_semana": 5, "abre": "10:00", "cierra": "14:00"}]

    from davincihub.reservas.rutas import resumen_horarios

    assert resumen_horarios(horarios) == [
        ("Lun–Vie", "09:00–21:00"),
        ("Sáb", "10:00–14:00"),
    ]