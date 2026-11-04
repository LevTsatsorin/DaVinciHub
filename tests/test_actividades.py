import pytest

from davincihub import db
from davincihub.actividades.datos import (
    ErrorActividad,
    aprobar_actividad,
    crear_actividad,
    listar_actividades_creador,
    listar_actividades_publicas,
    obtener_actividad,
    rechazar_actividad,
)
from davincihub.reservas import datos as reservas


def login(client, email="mica@davinci.edu.ar", password="davinci123"):
    return client.post("/auth/login", data={"email": email, "password": password})


def login_admin(client):
    return login(client, email="admin@davinci.edu.ar", password="davinci123")


@pytest.fixture(autouse=True)
def sala_abierta(app):
    with app.app_context():
        espacio_id = reservas.crear_espacio("Sala Abierta", capacidad=60)
        reservas.reemplazar_horarios_espacio(
            espacio_id, [{"dia_semana": d, "abre": "08:00", "cierra": "23:00"} for d in range(7)])


def _sala(app=None):
    if app is not None:
        with app.app_context():
            return _sala()
    return db.query_one("SELECT id FROM espacios WHERE nombre = 'Sala Abierta'")["id"]


def _obtener_ids_estudiantes(app):
    with app.app_context():
        u1 = db.query_one("SELECT id FROM usuarios WHERE email = 'mica@davinci.edu.ar'")
        u2 = db.query_one("SELECT id FROM usuarios WHERE email = 'tomas@davinci.edu.ar'")
        return u1["id"], u2["id"]


# --- Tests de Capa de Datos ---


def test_crear_actividad_queda_pendiente(app):
    u1_id, _ = _obtener_ids_estudiantes(app)
    with app.app_context():
        act_id = crear_actividad(
            creador_id=u1_id,
            nombre="Torneo de Smash Bros",
            descripcion="Torneo presencial en el aula magna.",
            inicio="2029-11-20T16:00:00",
            fin="2029-11-20T20:00:00",
            espacio_id=_sala(),
            cupo_maximo=32,
        )
        assert act_id >= 1

        act = obtener_actividad(act_id)
        assert act is not None
        assert act["nombre"] == "Torneo de Smash Bros"
        assert act["estado"] == "pendiente"
        assert act["motivo_rechazo"] is None


def test_no_se_crean_actividades_en_el_pasado(app):
    u1_id, _ = _obtener_ids_estudiantes(app)
    with app.app_context(), pytest.raises(ErrorActividad, match="pasado"):
        crear_actividad(
            creador_id=u1_id,
            nombre="Encuentro Pasado",
            descripcion="No debe permitirse.",
            inicio="2020-01-01T10:00:00",
            fin="2020-01-01T22:00:00",
            espacio_id=_sala(),
            cupo_maximo=10,
        )


def test_ciclo_aprobacion_notifica_al_creador(app):
    u1_id, _ = _obtener_ids_estudiantes(app)
    with app.app_context():
        act_id = crear_actividad(
            creador_id=u1_id,
            nombre="Taller de Blender 3D",
            descripcion="Modelado orgánico básico.",
            inicio="2029-12-05T14:00:00",
            fin="2029-12-05T22:00:00",
            espacio_id=_sala(),
            cupo_maximo=20,
        )

        # Pendiente no debe figurar en el listado público (RN-11)
        publicas_antes = listar_actividades_publicas()
        ids_publicas = [a["id"] for a in publicas_antes]
        assert act_id not in ids_publicas

        # Aprobar
        ok = aprobar_actividad(act_id)
        assert ok is True

        act_aprobada = obtener_actividad(act_id)
        assert act_aprobada["estado"] == "aprobada"

        # Ahora sí figura en el listado público
        publicas_despues = listar_actividades_publicas()
        assert act_id in [a["id"] for a in publicas_despues]

        # Notificación al creador
        notif = db.query_one(
            "SELECT * FROM notificaciones WHERE usuario_id = :u ORDER BY id DESC LIMIT 1",
            u=u1_id,
        )
        assert notif is not None
        assert notif["tipo"] == "actividades"
        assert "aprobada" in notif["cuerpo"].lower()


def test_rechazo_exige_motivo_y_notifica_al_creador(app):
    u1_id, _ = _obtener_ids_estudiantes(app)
    with app.app_context():
        act_id = crear_actividad(
            creador_id=u1_id,
            nombre="Fiesta no autorizada",
            descripcion="Encuentro social sin permiso.",
            inicio="2029-12-10T22:00:00",
            fin="2029-12-10T23:00:00",
            espacio_id=_sala(),
            cupo_maximo=50,
        )

        # Sin motivo falla (RF-22)
        with pytest.raises(ErrorActividad, match="motivo"):
            rechazar_actividad(act_id, motivo="   ")

        # Con motivo válido
        ok = rechazar_actividad(act_id, motivo="No cumple con el reglamento de convivencia.")
        assert ok is True

        act_rechazada = obtener_actividad(act_id)
        assert act_rechazada["estado"] == "rechazada"
        assert act_rechazada["motivo_rechazo"] == "No cumple con el reglamento de convivencia."

        # No está en el listado público
        assert act_id not in [a["id"] for a in listar_actividades_publicas()]

        # Notificación al creador con el motivo
        notif = db.query_one(
            "SELECT * FROM notificaciones WHERE usuario_id = :u ORDER BY id DESC LIMIT 1",
            u=u1_id,
        )
        assert "rechazada" in notif["cuerpo"].lower()
        assert "reglamento de convivencia" in notif["cuerpo"]


def test_creador_ve_el_estado_de_sus_actividades(app):
    u1_id, u2_id = _obtener_ids_estudiantes(app)
    with app.app_context():
        a1 = crear_actividad(
            creador_id=u1_id,
            nombre="Actividad de Mica",
            descripcion="Desc",
            inicio="2029-10-10T10:00:00",
            fin="2029-10-10T22:00:00",
            espacio_id=_sala(),
            cupo_maximo=15,
        )
        a2 = crear_actividad(
            creador_id=u2_id,
            nombre="Actividad de Tomas",
            descripcion="Desc",
            inicio="2029-10-12T10:00:00",
            fin="2029-10-12T22:00:00",
            espacio_id=_sala(),
            cupo_maximo=15,
        )

        mis_actividades_u1 = listar_actividades_creador(u1_id)
        ids_u1 = [a["id"] for a in mis_actividades_u1]
        assert a1 in ids_u1
        assert a2 not in ids_u1


# --- Tests de Vistas, Permisos y Criterios de Aceptación ---


def test_actividad_pendiente_no_aparece_en_listado_publico(client, app):
    u1_id, _ = _obtener_ids_estudiantes(app)
    with app.app_context():
        crear_actividad(
            creador_id=u1_id,
            nombre="Actividad Oculta Pendiente",
            descripcion="No debe verse en /actividades",
            inicio="2029-10-20T10:00:00",
            fin="2029-10-20T22:00:00",
            espacio_id=_sala(),
            cupo_maximo=20,
        )

    res = client.get("/actividades/")
    assert res.status_code == 200
    assert "Actividad Oculta Pendiente" not in res.get_data(as_text=True)


def test_actividad_pendiente_no_accesible_por_url_directa_para_otros_estudiantes_ca08(client, app):
    """Criterio de aceptación CA-08:

    Una actividad pendiente no aparece en el listado público ni por URL directa para otros estudiantes.
    """
    u1_id, _ = _obtener_ids_estudiantes(app)
    with app.app_context():
        act_id = crear_actividad(
            creador_id=u1_id,
            nombre="Charla Secreta",
            descripcion="Detalles aún no aprobados",
            inicio="2029-10-20T10:00:00",
            fin="2029-10-20T22:00:00",
            espacio_id=_sala(),
            cupo_maximo=20,
        )

    # 1. Visitante anónimo recibe 404
    res_anonimo = client.get(f"/actividades/{act_id}")
    assert res_anonimo.status_code == 404

    # 2. Otro estudiante (Tomás) logueado intenta entrar directo por URL y recibe 404
    login(client, email="tomas@davinci.edu.ar", password="davinci123")
    res_otro = client.get(f"/actividades/{act_id}")
    assert res_otro.status_code == 404
    client.post("/auth/salir")

    # 3. El creador (Mica) sí puede verla
    login(client, email="mica@davinci.edu.ar", password="davinci123")
    res_creador = client.get(f"/actividades/{act_id}")
    assert res_creador.status_code == 200
    assert "Charla Secreta" in res_creador.get_data(as_text=True)
    client.post("/auth/salir")

    # 4. El admin sí puede verla para moderar
    login_admin(client)
    res_admin = client.get(f"/actividades/{act_id}")
    assert res_admin.status_code == 200
    assert "Charla Secreta" in res_admin.get_data(as_text=True)


def test_flujo_completo_crear_y_aprobar_por_web(client, app):
    _u1_id, _ = _obtener_ids_estudiantes(app)

    # Estudiante crea propuesta
    login(client, email="mica@davinci.edu.ar", password="davinci123")
    post_res = client.post(
        "/actividades/crear",
        data={
            "nombre": "Torneo de Rocket League",
            "descripcion": "Torneo 2v2 en el laboratorio de informática.",
            "espacio_id": str(_sala(app)),
            "fecha": "2029-11-01",
            "inicio": "15:00",
            "fin": "18:00",
            "cupo_maximo": "16",
        },
    )
    assert post_res.status_code == 302
    assert "/actividades/mis-actividades" in post_res.headers["Location"]
    client.post("/auth/salir")

    with app.app_context():
        act = db.query_one("SELECT * FROM actividades WHERE nombre = 'Torneo de Rocket League'")
        assert act is not None
        assert act["estado"] == "pendiente"
        act_id = act["id"]

    # Admin modera y aprueba
    login_admin(client)
    admin_panel_res = client.get("/actividades/admin")
    assert admin_panel_res.status_code == 200
    assert "Torneo de Rocket League" in admin_panel_res.get_data(as_text=True)

    aprob_res = client.post(f"/actividades/admin/{act_id}/aprobar")
    assert aprob_res.status_code == 302
    client.post("/auth/salir")

    # Ahora es pública para cualquiera
    publico_res = client.get("/actividades/?mes=2029-11")
    assert "Torneo de Rocket League" in publico_res.get_data(as_text=True)


def test_rechazo_desde_panel_admin(client, app):
    u1_id, _ = _obtener_ids_estudiantes(app)
    with app.app_context():
        act_id = crear_actividad(
            creador_id=u1_id,
            nombre="Actividad a Rechazar",
            descripcion="Descripción de prueba",
            inicio="2029-11-15T18:00:00",
            fin="2029-11-15T22:00:00",
            espacio_id=_sala(),
            cupo_maximo=10,
        )

    login_admin(client)
    rech_res = client.post(
        f"/actividades/admin/{act_id}/rechazar",
        data={"motivo": "Espacio no disponible en esa fecha."},
    )
    assert rech_res.status_code == 302

    with app.app_context():
        act = obtener_actividad(act_id)
        assert act["estado"] == "rechazada"
        assert act["motivo_rechazo"] == "Espacio no disponible en esa fecha."
