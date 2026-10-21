import pytest

from davincihub import db
from davincihub.reservas import datos, rutas


def login(client, email="mica@davinci.edu.ar"):
    return client.post("/auth/login", data={"email": email, "password": "davinci123"})


@pytest.fixture
def sala(app):
    with app.app_context():
        espacio_id = datos.crear_espacio("Sala Nocturna")
        datos.reemplazar_horarios_espacio(
            espacio_id, [{"dia_semana": d, "abre": "08:00", "cierra": "23:59"} for d in range(7)]
        )
        return espacio_id


@pytest.fixture
def martes_22_30(monkeypatch):
    monkeypatch.setattr(datos, "ahora_local", lambda: "2026-10-20T22:30:00")


def test_reserva_de_la_misma_noche_no_es_pasado(app, sala, martes_22_30):
    with app.app_context():
        assert datos.crear_reserva(sala, 2, "2026-10-20T23:00", "2026-10-20T23:30") > 0


def test_reserva_anterior_a_la_hora_local_es_pasado(app, sala, martes_22_30):
    with app.app_context(), pytest.raises(datos.ErrorHorarioInvalido, match="pasado"):
        datos.crear_reserva(sala, 2, "2026-10-20T22:00", "2026-10-20T22:20")


def test_se_puede_cancelar_hasta_la_hora_local_de_inicio(app, sala, martes_22_30):
    with app.app_context():
        reserva = datos.crear_reserva(sala, 2, "2026-10-20T23:00", "2026-10-20T23:30")
        proximas = datos.listar_reservas_usuario(2, solo_futuras=True)
        de_la_sala = [r for r in proximas if r["espacio_id"] == sala]
        assert [r["id"] for r in de_la_sala] == [reserva]
        assert de_la_sala[0]["puede_cancelar"] is True
        assert datos.cancelar_reserva(reserva, 2) is True


def test_detalle_usa_la_fecha_local(client, sala, monkeypatch):
    monkeypatch.setattr(rutas, "hoy_local", lambda: "2026-10-20")
    login(client)
    assert 'value="2026-10-20"' in client.get(f"/espacios/{sala}").get_data(as_text=True)


def test_enlace_del_aviso_de_reserva_funciona(client, app, sala):
    with app.app_context():
        datos.crear_reserva(sala, 2, "2030-01-07T10:00", "2030-01-07T11:00")
        enlace = db.query_one(
            "SELECT enlace FROM notificaciones WHERE usuario_id = 2 ORDER BY id DESC LIMIT 1"
        )["enlace"]
    login(client)
    assert client.get(enlace).status_code == 200


def test_enlace_del_aviso_de_cancelacion_funciona(client, app, sala):
    with app.app_context():
        reserva = datos.crear_reserva(sala, 2, "2030-01-07T10:00", "2030-01-07T11:00")
        datos.cancelar_reserva(reserva, 2)
        enlace = db.query_one(
            "SELECT enlace FROM notificaciones WHERE usuario_id = 2 ORDER BY id DESC LIMIT 1"
        )["enlace"]
    login(client)
    assert client.get(enlace).status_code == 200


def test_crear_reserva_bloquea_la_fila_del_espacio(app, sala, monkeypatch):
    llamadas = []
    original = db.bloquear_fila

    def espiar(tabla, fila_id):
        llamadas.append((tabla, fila_id))
        return original(tabla, fila_id)

    monkeypatch.setattr(db, "bloquear_fila", espiar)
    with app.app_context():
        datos.crear_reserva(sala, 2, "2030-01-07T10:00", "2030-01-07T11:00")
    assert llamadas == [("espacios", sala)]


@pytest.mark.parametrize(("iso", "texto"), [("2026-10-21T09:00:00", "Mié 21/10"),
                                             ("2026-10-25T18:30:00", "Dom 25/10")])
def test_dia_y_fecha(iso, texto):
    assert rutas.dia_y_fecha(iso) == texto


def test_mis_reservas_muestra_fecha_legible_y_pide_confirmacion(client, app, sala):
    with app.app_context():
        datos.crear_reserva(sala, 2, "2030-01-07T10:00", "2030-01-07T11:00")
    login(client)
    texto = client.get("/reservas/mis-reservas/").get_data(as_text=True)
    assert "Lun 07/01" in texto
    assert "2030-01-07 ·" not in texto
    assert "data-confirmar=" in texto


def test_todas_las_reservas_no_repite_espacios_vacios(client, app, sala):
    with app.app_context():
        datos.crear_reserva(sala, 2, "2030-01-07T10:00", "2030-01-07T11:00")
    login(client, "admin@davinci.edu.ar")
    texto = client.get("/admin/reservas/").get_data(as_text=True)
    assert "Sala Nocturna" in texto
    assert "todavía no tiene reservas" not in texto
    assert "Sin reservas" not in texto


@pytest.fixture
def servidor_en_utc(monkeypatch):
    import time

    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.mark.parametrize("iso", ["2026-10-20T22:30:00", "2026-10-21T01:30:00+00:00"])
def test_fecha_corta_en_un_servidor_utc(servidor_en_utc, iso):
    from davincihub.utiles import fecha_corta

    assert fecha_corta(iso) == "20/10 22:30"


def test_fecha_sin_ceros_no_esconde_las_reservas(app, sala):
    with app.app_context():
        datos.crear_reserva(sala, 2, "2030-01-07T10:00", "2030-01-07T11:00")
        disponibilidad = datos.obtener_disponibilidad_dia(sala, "2030-1-7")
    assert disponibilidad["fecha"] == "2030-01-07"
    assert len(disponibilidad["reservas_ocupadas"]) == 1


def test_detalle_normaliza_la_fecha(client, sala):
    login(client)
    assert 'value="2030-01-07"' in client.get(f"/espacios/{sala}?fecha=2030-1-7").get_data(as_text=True)


def test_cancelar_bloquea_la_fila_de_la_reserva(app, sala, monkeypatch):
    with app.app_context():
        reserva = datos.crear_reserva(sala, 2, "2030-01-07T10:00", "2030-01-07T11:00")
    llamadas = []
    original = db.bloquear_fila
    monkeypatch.setattr(db, "bloquear_fila", lambda t, i: llamadas.append((t, i)) or original(t, i))
    with app.app_context():
        datos.cancelar_reserva(reserva, 2)
    assert ("reservas", reserva) in llamadas


def _aviso_roto(*args, **kwargs):
    raise RuntimeError("sin avisos")


def test_si_falla_el_aviso_la_reserva_no_queda_a_medias(app, sala, monkeypatch):
    from davincihub import notificaciones

    monkeypatch.setattr(notificaciones, "notificar", _aviso_roto)
    with app.app_context():
        with pytest.raises(RuntimeError):
            datos.crear_reserva(sala, 2, "2030-01-07T10:00", "2030-01-07T11:00")
        assert db.query_one("SELECT COUNT(*) AS n FROM reservas WHERE espacio_id = :e", e=sala)["n"] == 0


def test_si_falla_el_aviso_la_cancelacion_no_queda_a_medias(app, sala, monkeypatch):
    from davincihub import notificaciones

    with app.app_context():
        reserva = datos.crear_reserva(sala, 2, "2030-01-07T10:00", "2030-01-07T11:00")
    monkeypatch.setattr(notificaciones, "notificar", _aviso_roto)
    with app.app_context():
        with pytest.raises(RuntimeError):
            datos.cancelar_reserva(reserva, 2)
        assert datos.obtener_reserva(reserva)["estado"] == "confirmada"


def test_mis_reservas_conserva_las_canceladas(client, app, sala):
    with app.app_context():
        reserva = datos.crear_reserva(sala, 2, "2030-01-07T10:00", "2030-01-07T11:00", motivo="Ensayo")
        datos.cancelar_reserva(reserva, 2)
    login(client)
    texto = client.get("/reservas/mis-reservas/").get_data(as_text=True)
    assert "Historial" in texto
    assert "Ensayo" in texto
    assert "reserva-estado-cancelada" in texto


def test_hora_con_zona_se_pasa_a_hora_local(app, sala):
    with app.app_context():
        reserva = datos.crear_reserva(sala, 2, "2030-01-07T13:00:00+00:00", "2030-01-07T14:00:00+00:00")
        assert datos.obtener_reserva(reserva)["inicio"] == "2030-01-07T10:00:00"


def test_segundos_despues_del_cierre_quedan_fuera_de_franja(app, sala):
    with app.app_context(), pytest.raises(datos.ErrorHorarioInvalido):
        datos.crear_reserva(sala, 2, "2030-01-07T23:00", "2030-01-07T23:59:30")


def test_una_fecha_pasada_avisa_y_lleva_a_un_dia_futuro(client, sala, monkeypatch):
    monkeypatch.setattr(rutas, "hoy_local", lambda: "2030-01-07")
    login(client)
    texto = client.get(f"/espacios/{sala}?fecha=2030-01-01").get_data(as_text=True)
    assert "Ese día ya pasó" in texto
    assert "No quedan horarios libres" not in texto
    assert "?fecha=2030-01-07" in texto
    assert "?fecha=2030-01-02" not in texto


def test_historial_se_limita_en_la_consulta(app, sala):
    with app.app_context():
        for dia in range(1, 13):
            reserva = datos.crear_reserva(sala, 2, f"2030-01-{dia:02d}T10:00", f"2030-01-{dia:02d}T11:00")
            datos.cancelar_reserva(reserva, 2)
        historial = datos.listar_historial_usuario(2, limite=10)
    assert len(historial) == 10
    assert historial[0]["inicio"] == "2030-01-12T10:00:00"


def test_a_hora_local_vive_en_utiles():
    from datetime import UTC, datetime

    from davincihub.utiles import a_hora_local

    assert a_hora_local(datetime(2030, 1, 7, 13, 0, tzinfo=UTC)) == datetime(2030, 1, 7, 10, 0)
    assert a_hora_local(datetime(2030, 1, 7, 10, 0)) == datetime(2030, 1, 7, 10, 0)


def test_laboratorio_3d_abre_la_tarde_del_viernes(app):
    with app.app_context():
        espacio = db.query_one("SELECT id FROM espacios WHERE nombre LIKE 'Laboratorio de Maquetado%'")
        franjas = db.query(
            "SELECT abre, cierra FROM horarios_espacios WHERE espacio_id = :e AND dia_semana = 4 ORDER BY abre",
            e=espacio["id"],
        )
    assert [(f["abre"], f["cierra"]) for f in franjas] == [("09:00", "13:00"), ("14:00", "18:00")]
