from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest

from davincihub import db
from davincihub.actividades import datos


def crear_actividad(app, cupo_maximo=2):
    with app.app_context():
        creador = db.query_one(
            "SELECT id FROM usuarios WHERE email = :email", email="admin@davinci.edu.ar"
        )
        usuarios = {
            fila["email"]: fila["id"]
            for fila in db.query("SELECT id, email FROM usuarios WHERE rol = 'estudiante'")
        }
        actividad_id = datos.crear_actividad(
            creador_id=creador["id"],
            nombre="Actividad de prueba",
            descripcion="Descripción de prueba",
            inicio=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
            fin=None,
            ubicacion="Aula de prueba",
            cupo_maximo=cupo_maximo,
        )
        datos.cambiar_estado(actividad_id, "aprobada")
    return actividad_id, creador["id"], usuarios


def test_inscripciones_simultaneas_al_ultimo_lugar_solo_acepta_una(app):
    actividad_id, creador_id, usuarios = crear_actividad(app, cupo_maximo=1)
    participantes = [usuarios["mica@davinci.edu.ar"], usuarios["tomas@davinci.edu.ar"]]
    inicio_simultaneo = Barrier(2)

    def intentar_inscripcion(usuario_id):
        with app.app_context():
            inicio_simultaneo.wait()
            try:
                datos.inscribir(actividad_id, usuario_id)
                return True
            except datos.ErrorInscripcion:
                return False

    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        resultados = list(ejecutor.map(intentar_inscripcion, participantes))

    assert sum(resultados) == 1
    with app.app_context():
        actividad = datos.obtener_actividad(actividad_id)
        notificacion = db.query_one(
            "SELECT COUNT(*) AS total FROM notificaciones "
            "WHERE usuario_id = :usuario_id AND enlace = :enlace",
            usuario_id=creador_id,
            enlace=f"/actividades/{actividad_id}/inscriptos",
        )
    assert actividad["inscriptos"] == 1
    assert actividad["cupo_disponible"] == 0
    assert notificacion["total"] == 1


def test_dar_de_baja_libera_el_cupo(app):
    actividad_id, _, usuarios = crear_actividad(app, cupo_maximo=1)
    estudiante_id = usuarios["mica@davinci.edu.ar"]

    with app.app_context():
        datos.inscribir(actividad_id, estudiante_id)
        datos.dar_de_baja(actividad_id, estudiante_id)

        assert not datos.esta_inscripto(actividad_id, estudiante_id)
        assert datos.obtener_actividad(actividad_id)["cupo_disponible"] == 1


def test_cancelar_actividad_notifica_a_los_inscriptos(app):
    actividad_id, _, usuarios = crear_actividad(app, cupo_maximo=1)
    estudiante_id = usuarios["mica@davinci.edu.ar"]

    with app.app_context():
        datos.inscribir(actividad_id, estudiante_id)
        datos.cambiar_estado(actividad_id, "cancelada")
        notificacion = db.query_one(
            "SELECT cuerpo FROM notificaciones "
            "WHERE usuario_id = :usuario_id AND enlace = :enlace",
            usuario_id=estudiante_id,
            enlace=f"/actividades/{actividad_id}",
        )

    assert "fue cancelada" in notificacion["cuerpo"]


def test_actividad_completa_no_acepta_mas_inscripciones_y_lo_muestra(client, app):
    actividad_id, _, usuarios = crear_actividad(app, cupo_maximo=1)
    with app.app_context():
        datos.inscribir(actividad_id, usuarios["mica@davinci.edu.ar"])
        with pytest.raises(datos.ErrorInscripcion, match="no tiene lugares disponibles"):
            datos.inscribir(actividad_id, usuarios["tomas@davinci.edu.ar"])

    client.post(
        "/auth/login",
        data={"email": "lucia@davinci.edu.ar", "password": "davinci123"},
    )
    respuesta = client.get(f"/actividades/{actividad_id}")

    assert respuesta.status_code == 200
    assert "Sin lugares disponibles" in respuesta.get_data(as_text=True)
    assert "Actividad completa" in respuesta.get_data(as_text=True)