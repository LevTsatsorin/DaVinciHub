import threading
from concurrent.futures import ThreadPoolExecutor

# pyrefly: ignore[missing-import]
import pytest

from davincihub import db
from davincihub.reservas.datos import (
    ErrorCancelacionInvalida,
    ErrorEspacio,
    ErrorHorarioInvalido,
    ErrorReserva,
    ErrorSuperposicionReserva,
    agregar_franja_horaria,
    cancelar_reserva,
    crear_espacio,
    crear_reserva,
    deshabilitar_espacio,
    listar_reservas_usuario,
    listar_todas_las_reservas,
    obtener_disponibilidad_dia,
    obtener_reserva,
)
from davincihub.utiles import ahora


def _crear_espacio_prueba(app):
    with app.app_context():
        # Crear espacio abierto de Lunes a Domingo de 08:00 a 22:00
        esp_id = crear_espacio(nombre="Laboratorio Mocap D2", capacidad=15)
        for dia in range(7):
            agregar_franja_horaria(esp_id, dia, "08:00", "22:00")
        usuario = db.query_one("SELECT id FROM usuarios WHERE rol = 'estudiante' LIMIT 1")
        usuario2 = db.query_one("SELECT id FROM usuarios WHERE rol = 'estudiante' AND id <> :id LIMIT 1", id=usuario["id"])
        return esp_id, usuario["id"], usuario2["id"]


def test_crear_reserva_confirmada_al_instante(app):
    esp_id, u1_id, _ = _crear_espacio_prueba(app)
    with app.app_context():
        # Reserva futura válida (ej. año 2029)
        reserva_id = crear_reserva(
            espacio_id=esp_id,
            usuario_id=u1_id,
            inicio="2029-05-10T10:00:00",
            fin="2029-05-10T12:00:00",
        )
        assert reserva_id >= 1

        reserva = obtener_reserva(reserva_id)
        assert reserva is not None
        assert reserva["estado"] == "confirmada"
        assert reserva["espacio_id"] == esp_id
        assert reserva["usuario_id"] == u1_id

        # Notificación enviada al estudiante
        notif = db.query_one(
            "SELECT * FROM notificaciones WHERE usuario_id = :u ORDER BY id DESC LIMIT 1",
            u=u1_id,
        )
        assert notif is not None
        assert notif["tipo"] == "reservas"
        assert "confirmada" in notif["cuerpo"].lower()


def test_no_se_reserva_en_el_pasado(app):
    esp_id, u1_id, _ = _crear_espacio_prueba(app)
    with app.app_context(), pytest.raises(ErrorHorarioInvalido, match="pasado"):
        crear_reserva(
            espacio_id=esp_id,
            usuario_id=u1_id,
            inicio="2020-01-01T10:00:00",
            fin="2020-01-01T12:00:00",
        )


def test_no_se_reserva_fuera_del_horario_del_espacio(app):
    esp_id, u1_id, _ = _crear_espacio_prueba(app)
    with app.app_context():
        # Fuera de rango horario (abre 08:00, pide desde las 06:00)
        with pytest.raises(ErrorHorarioInvalido, match="fuera de las franjas"):
            crear_reserva(
                espacio_id=esp_id,
                usuario_id=u1_id,
                inicio="2029-05-10T06:00:00",
                fin="2029-05-10T09:00:00",
            )

        # Cierra 22:00, pide hasta 23:00
        with pytest.raises(ErrorHorarioInvalido, match="fuera de las franjas"):
            crear_reserva(
                espacio_id=esp_id,
                usuario_id=u1_id,
                inicio="2029-05-10T20:00:00",
                fin="2029-05-10T23:00:00",
            )


def test_espacio_deshabilitado_no_admite_nuevas_reservas(app):
    esp_id, u1_id, _ = _crear_espacio_prueba(app)
    with app.app_context():
        deshabilitar_espacio(esp_id)
        with pytest.raises(ErrorEspacio, match="deshabilitado"):
            crear_reserva(
                espacio_id=esp_id,
                usuario_id=u1_id,
                inicio="2029-05-10T10:00:00",
                fin="2029-05-10T12:00:00",
            )


def test_dos_reservas_superpuestas_falla_segunda(app):
    esp_id, u1_id, u2_id = _crear_espacio_prueba(app)
    with app.app_context():
        # Primera reserva 10:00 a 12:00
        r1 = crear_reserva(
            espacio_id=esp_id,
            usuario_id=u1_id,
            inicio="2029-05-10T10:00:00",
            fin="2029-05-10T12:00:00",
        )
        assert r1 >= 1

        # Intento con solapamiento parcial (11:00 a 13:00)
        with pytest.raises(ErrorSuperposicionReserva):
            crear_reserva(
                espacio_id=esp_id,
                usuario_id=u2_id,
                inicio="2029-05-10T11:00:00",
                fin="2029-05-10T13:00:00",
            )

        # Intento contenido adentro (10:30 a 11:30)
        with pytest.raises(ErrorSuperposicionReserva):
            crear_reserva(
                espacio_id=esp_id,
                usuario_id=u2_id,
                inicio="2029-05-10T10:30:00",
                fin="2029-05-10T11:30:00",
            )

        # Intento consecutivo (12:00 a 14:00) -> permitido!
        r2 = crear_reserva(
            espacio_id=esp_id,
            usuario_id=u2_id,
            inicio="2029-05-10T12:00:00",
            fin="2029-05-10T14:00:00",
        )
        assert r2 >= 1


def test_simulacion_dos_reservas_simultaneas_mismo_turno_ca07(app):
    """Criterio de aceptación CA-07:

    Simula dos reservas concurrentes del mismo turno y verifica que sólo una queda confirmada.
    """
    esp_id, u1_id, u2_id = _crear_espacio_prueba(app)

    barrera = threading.Barrier(2)
    resultados = []
    errores = []

    def intentar_reserva(uid):
        with app.app_context():
            try:
                barrera.wait(timeout=5)
                rid = crear_reserva(
                    espacio_id=esp_id,
                    usuario_id=uid,
                    inicio="2029-06-15T14:00:00",
                    fin="2029-06-15T16:00:00",
                )
                resultados.append((uid, rid))
            except ErrorReserva as e:
                errores.append((uid, e))

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(intentar_reserva, u1_id)
        f2 = executor.submit(intentar_reserva, u2_id)
        f1.result()
        f2.result()

    # Exactamente una tuvo éxito y la otra falló por superposición
    assert len(resultados) == 1, f"Se confirmaron {len(resultados)}: {resultados}"
    assert len(errores) == 1, f"Hubo {len(errores)} errores: {errores}"
    assert isinstance(errores[0][1], ErrorSuperposicionReserva)

    with app.app_context():
        confirmadas = db.query(
            "SELECT * FROM reservas WHERE espacio_id = :esp AND estado = 'confirmada'"
            " AND inicio = '2029-06-15T14:00:00'",
            esp=esp_id,
        )
        assert len(confirmadas) == 1


def test_cancelacion_reserva_propia_libera_espacio(app):
    """RF-21, RN-10:

    Cancela una reserva propia que no comenzó, queda como cancelada y libera el espacio.
    """
    esp_id, u1_id, u2_id = _crear_espacio_prueba(app)
    with app.app_context():
        rid = crear_reserva(
            espacio_id=esp_id,
            usuario_id=u1_id,
            inicio="2029-07-20T09:00:00",
            fin="2029-07-20T11:00:00",
        )

        # Cancelar
        ok = cancelar_reserva(rid, usuario_id=u1_id)
        assert ok is True

        reserva = obtener_reserva(rid)
        assert reserva["estado"] == "cancelada"

        # Notificación enviada al estudiante por cancelación
        notif = db.query_one(
            "SELECT * FROM notificaciones WHERE usuario_id = :u ORDER BY id DESC LIMIT 1",
            u=u1_id,
        )
        assert "cancelada" in notif["cuerpo"].lower()

        # El espacio queda liberado: u2 ahora sí puede reservar en ese mismo horario
        rid2 = crear_reserva(
            espacio_id=esp_id,
            usuario_id=u2_id,
            inicio="2029-07-20T09:00:00",
            fin="2029-07-20T11:00:00",
        )
        assert rid2 >= 1


def test_no_se_cancela_reserva_ajena(app):
    esp_id, u1_id, u2_id = _crear_espacio_prueba(app)
    with app.app_context():
        rid = crear_reserva(
            espacio_id=esp_id,
            usuario_id=u1_id,
            inicio="2029-08-01T10:00:00",
            fin="2029-08-01T12:00:00",
        )
        with pytest.raises(ErrorCancelacionInvalida, match="no es tuya"):
            cancelar_reserva(rid, usuario_id=u2_id)


def test_no_se_cancela_reserva_pasada_o_en_curso(app):
    esp_id, u1_id, _ = _crear_espacio_prueba(app)
    with app.app_context():
        # Insertar directamente reserva ya pasada
        fila = db.query_one(
            "INSERT INTO reservas (espacio_id, usuario_id, inicio, fin, estado, creado)"
            " VALUES (:esp, :u, '2020-01-01T10:00:00', '2020-01-01T12:00:00', 'confirmada', :creado)"
            " RETURNING id",
            esp=esp_id,
            u=u1_id,
            creado=ahora(),
        )
        rid_pasada = fila["id"]

        with pytest.raises(ErrorCancelacionInvalida, match="ya comenzó"):
            cancelar_reserva(rid_pasada, usuario_id=u1_id)


def test_disponibilidad_dia_muestra_libres_y_ocupadas(app):
    esp_id, u1_id, _ = _crear_espacio_prueba(app)
    with app.app_context():
        crear_reserva(
            espacio_id=esp_id,
            usuario_id=u1_id,
            inicio="2029-09-10T10:00:00",
            fin="2029-09-10T12:00:00",
        )

        disp = obtener_disponibilidad_dia(esp_id, "2029-09-10")
        assert disp["abierto"] is True
        assert len(disp["horarios_habilitados"]) >= 1
        assert len(disp["reservas_ocupadas"]) == 1
        assert disp["reservas_ocupadas"][0]["inicio"] == "2029-09-10T10:00:00"


def test_listar_reservas_usuario_y_admin(app):
    esp_id, u1_id, u2_id = _crear_espacio_prueba(app)
    with app.app_context():
        r1 = crear_reserva(
            espacio_id=esp_id,
            usuario_id=u1_id,
            inicio="2029-10-01T09:00:00",
            fin="2029-10-01T11:00:00",
        )
        r2 = crear_reserva(
            espacio_id=esp_id,
            usuario_id=u2_id,
            inicio="2029-10-01T14:00:00",
            fin="2029-10-01T16:00:00",
        )

        mis_reservas_u1 = listar_reservas_usuario(u1_id)
        ids_u1 = [r["id"] for r in mis_reservas_u1]
        assert r1 in ids_u1
        assert r2 not in ids_u1
        assert mis_reservas_u1[0]["puede_cancelar"] is True

        todas_admin = listar_todas_las_reservas()
        ids_admin = [r["id"] for r in todas_admin]
        assert r1 in ids_admin
        assert r2 in ids_admin
