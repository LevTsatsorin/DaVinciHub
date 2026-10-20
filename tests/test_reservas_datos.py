import pytest

from davincihub import db
from davincihub.reservas.datos import (
    DIAS_SEMANA,
    ErrorEspacio,
    ErrorFranjaHoraria,
    ErrorSuperposicionHoraria,
    actualizar_espacio,
    agregar_franja_horaria,
    crear_espacio,
    deshabilitar_espacio,
    eliminar_franja_horaria,
    espacio_admite_reservas,
    habilitar_espacio,
    hay_superposicion,
    listar_espacios_admin,
    listar_espacios_catalogo,
    obtener_espacio,
    obtener_horarios_espacio,
    reemplazar_horarios_espacio,
    validar_formato_hora,
    validar_franja,
    validar_lista_franjas,
)


def test_crear_espacio_ok(app):
    with app.app_context():
        nuevo_id = crear_espacio(
            nombre="Laboratorio de Inteligencia Artificial",
            descripcion="PCs con GPUs para entrenamiento de modelos",
            capacidad=20,
        )
        assert nuevo_id >= 1

        espacio = obtener_espacio(nuevo_id)
        assert espacio is not None
        assert espacio["nombre"] == "Laboratorio de Inteligencia Artificial"
        assert espacio["descripcion"] == "PCs con GPUs para entrenamiento de modelos"
        assert espacio["capacidad"] == 20
        assert espacio["activo"] == 1


def test_crear_espacio_sin_nombre(app):
    with app.app_context(), pytest.raises(ErrorEspacio, match="obligatorio"):
        crear_espacio(nombre="   ")


def test_crear_espacio_capacidad_invalida(app):
    with app.app_context():
        with pytest.raises(ErrorEspacio, match="mayor a 0"):
            crear_espacio(nombre="Sala Invalida", capacidad=0)
        with pytest.raises(ErrorEspacio, match="mayor a 0"):
            crear_espacio(nombre="Sala Invalida 2", capacidad=-5)


def test_crear_espacio_nombre_duplicado(app):
    with app.app_context():
        crear_espacio(nombre="Espacio Único")
        with pytest.raises(ErrorEspacio, match="Ya existe un espacio"):
            crear_espacio(nombre="Espacio Único")


def test_actualizar_espacio_ok(app):
    with app.app_context():
        esp_id = crear_espacio(nombre="Espacio Modificable", capacidad=15)
        ok = actualizar_espacio(
            esp_id,
            nombre="Espacio Modificado",
            descripcion="Nueva descripción",
            capacidad=25,
        )
        assert ok is True

        espacio = obtener_espacio(esp_id)
        assert espacio["nombre"] == "Espacio Modificado"
        assert espacio["descripcion"] == "Nueva descripción"
        assert espacio["capacidad"] == 25


def test_actualizar_espacio_inexistente(app):
    with app.app_context(), pytest.raises(ErrorEspacio, match="No existe"):
        actualizar_espacio(99999, nombre="Cualquiera")


def test_deshabilitar_y_habilitar_espacio(app):
    with app.app_context():
        esp_id = crear_espacio(nombre="Espacio Para Deshabilitar")
        assert espacio_admite_reservas(esp_id) is True

        deshabilitar_espacio(esp_id)
        assert espacio_admite_reservas(esp_id) is False

        espacio = obtener_espacio(esp_id)
        assert espacio["activo"] == 0

        habilitar_espacio(esp_id)
        assert espacio_admite_reservas(esp_id) is True


def test_deshabilitar_espacio_conserva_reservas_existentes(app):
    with app.app_context():
        # Crear espacio y simular una reserva existente previa
        esp_id = crear_espacio(nombre="Aula Magna Con Reserva")
        usuario = db.query_one("SELECT id FROM usuarios LIMIT 1")

        reserva = db.query_one(
            "INSERT INTO reservas (espacio_id, usuario_id, inicio, fin, creado)"
            " VALUES (:espacio, :usuario, :inicio, :fin, :creado) RETURNING id",
            espacio=esp_id,
            usuario=usuario["id"],
            inicio="2026-10-25T10:00:00",
            fin="2026-10-25T12:00:00",
            creado="2026-10-20T10:00:00",
        )
        reserva_id = reserva["id"]

        # Deshabilitar el espacio
        deshabilitar_espacio(esp_id)

        # La reserva debe seguir existiendo intacta
        reserva_guardada = db.query_one("SELECT * FROM reservas WHERE id = :id", id=reserva_id)
        assert reserva_guardada is not None
        assert reserva_guardada["estado"] == "confirmada"
        assert reserva_guardada["espacio_id"] == esp_id

        # Pero el espacio ya no debe admitir nuevas reservas
        assert espacio_admite_reservas(esp_id) is False


def test_validar_formato_hora():
    assert validar_formato_hora("09:00") == "09:00"
    assert validar_formato_hora("23:59") == "23:59"
    assert validar_formato_hora(" 14:30 ") == "14:30"

    with pytest.raises(ErrorFranjaHoraria):
        validar_formato_hora("9:00")
    with pytest.raises(ErrorFranjaHoraria):
        validar_formato_hora("24:00")
    with pytest.raises(ErrorFranjaHoraria):
        validar_formato_hora("12:60")
    with pytest.raises(ErrorFranjaHoraria):
        validar_formato_hora("tarde")


def test_validar_franja_cierre_posterior_a_apertura():
    abre, cierra = validar_franja("09:00", "18:00")
    assert abre == "09:00"
    assert cierra == "18:00"

    with pytest.raises(ErrorFranjaHoraria, match="posterior a la de apertura"):
        validar_franja("18:00", "09:00")

    with pytest.raises(ErrorFranjaHoraria, match="posterior a la de apertura"):
        validar_franja("14:00", "14:00")


def test_hay_superposicion():
    # Se superponen
    assert hay_superposicion("09:00", "12:00", "10:00", "14:00") is True
    assert hay_superposicion("10:00", "14:00", "09:00", "12:00") is True
    assert hay_superposicion("09:00", "15:00", "10:00", "12:00") is True
    assert hay_superposicion("10:00", "12:00", "09:00", "15:00") is True

    # Consecutivos (no se superponen)
    assert hay_superposicion("09:00", "12:00", "12:00", "15:00") is False
    assert hay_superposicion("12:00", "15:00", "09:00", "12:00") is False

    # Disjuntos separados
    assert hay_superposicion("09:00", "11:00", "13:00", "15:00") is False


def test_validar_lista_franjas_superposicion_mismo_dia():
    franjas_validas = [
        {"dia_semana": 0, "abre": "09:00", "cierra": "12:00"},
        {"dia_semana": 0, "abre": "12:00", "cierra": "15:00"},
        {"dia_semana": 1, "abre": "09:00", "cierra": "12:00"},  # Mismo horario otro día: ok
    ]
    validadas = validar_lista_franjas(franjas_validas)
    assert len(validadas) == 3

    franjas_con_solapamiento = [
        {"dia_semana": 2, "abre": "10:00", "cierra": "14:00"},
        {"dia_semana": 2, "abre": "13:00", "cierra": "16:00"},
    ]
    with pytest.raises(ErrorSuperposicionHoraria, match="se superponen"):
        validar_lista_franjas(franjas_con_solapamiento)


def test_agregar_franja_horaria_ok(app):
    with app.app_context():
        esp_id = crear_espacio(nombre="Estudio de Grabación Nuevo")

        # Lunes de 09:00 a 13:00
        h1 = agregar_franja_horaria(esp_id, dia_semana=0, abre="09:00", cierra="13:00")
        assert h1 >= 1

        # Lunes de 13:00 a 18:00 (consecutivo, permitido)
        h2 = agregar_franja_horaria(esp_id, dia_semana=0, abre="13:00", cierra="18:00")
        assert h2 >= 1

        # Martes de 09:00 a 13:00 (mismo horario en otro día, permitido)
        h3 = agregar_franja_horaria(esp_id, dia_semana=1, abre="09:00", cierra="13:00")
        assert h3 >= 1

        horarios = obtener_horarios_espacio(esp_id)
        assert len(horarios) == 3
        assert horarios[0]["dia_nombre"] == "Lunes"
        assert horarios[2]["dia_nombre"] == "Martes"


def test_agregar_franja_horaria_superposicion_falla(app):
    with app.app_context():
        esp_id = crear_espacio(nombre="Sala Test Superposición")
        agregar_franja_horaria(esp_id, dia_semana=3, abre="10:00", cierra="14:00")

        # Intento 1: se solapa al final
        with pytest.raises(ErrorSuperposicionHoraria, match="se superpone"):
            agregar_franja_horaria(esp_id, dia_semana=3, abre="13:00", cierra="16:00")

        # Intento 2: se solapa al principio
        with pytest.raises(ErrorSuperposicionHoraria, match="se superpone"):
            agregar_franja_horaria(esp_id, dia_semana=3, abre="09:00", cierra="11:00")

        # Intento 3: queda contenida adentro
        with pytest.raises(ErrorSuperposicionHoraria, match="se superpone"):
            agregar_franja_horaria(esp_id, dia_semana=3, abre="11:00", cierra="13:00")

        # Intento 4: envuelve a la existente
        with pytest.raises(ErrorSuperposicionHoraria, match="se superpone"):
            agregar_franja_horaria(esp_id, dia_semana=3, abre="08:00", cierra="18:00")

        # Solo debe quedar la franja original
        horarios = obtener_horarios_espacio(esp_id)
        assert len(horarios) == 1


def test_reemplazar_horarios_espacio_atomico(app):
    with app.app_context():
        esp_id = crear_espacio(nombre="Laboratorio Reemplazo")
        agregar_franja_horaria(esp_id, dia_semana=0, abre="09:00", cierra="12:00")

        nuevas_franjas = [
            {"dia_semana": 1, "abre": "14:00", "cierra": "18:00"},
            {"dia_semana": 2, "abre": "10:00", "cierra": "16:00"},
        ]
        reemplazar_horarios_espacio(esp_id, nuevas_franjas)

        horarios = obtener_horarios_espacio(esp_id)
        assert len(horarios) == 2
        dias = {h["dia_semana"] for h in horarios}
        assert dias == {1, 2}


def test_reemplazar_horarios_falla_mantiene_anteriores(app):
    with app.app_context():
        esp_id = crear_espacio(nombre="Laboratorio Atomicidad")
        agregar_franja_horaria(esp_id, dia_semana=0, abre="09:00", cierra="12:00")

        franjas_invalidas = [
            {"dia_semana": 1, "abre": "10:00", "cierra": "14:00"},
            {"dia_semana": 1, "abre": "12:00", "cierra": "16:00"},  # Superpuestas
        ]

        with pytest.raises(ErrorSuperposicionHoraria):
            reemplazar_horarios_espacio(esp_id, franjas_invalidas)

        # La transacción revierte y la franja original debe seguir estando
        horarios = obtener_horarios_espacio(esp_id)
        assert len(horarios) == 1
        assert horarios[0]["dia_semana"] == 0
        assert horarios[0]["abre"] == "09:00"


def test_eliminar_franja_horaria(app):
    with app.app_context():
        esp_id = crear_espacio(nombre="Espacio Eliminar Franja")
        h_id = agregar_franja_horaria(esp_id, dia_semana=4, abre="10:00", cierra="15:00")

        assert eliminar_franja_horaria(h_id) is True
        assert len(obtener_horarios_espacio(esp_id)) == 0


def test_catalogo_vs_admin_listados(app):
    with app.app_context():
        activo_id = crear_espacio(nombre="Espacio Visible", capacidad=30, activo=1)
        inactivo_id = crear_espacio(nombre="Espacio Oculto", capacidad=10, activo=0)
        agregar_franja_horaria(activo_id, dia_semana=0, abre="09:00", cierra="18:00")

        catalogo = listar_espacios_catalogo()
        ids_catalogo = [e["id"] for e in catalogo]
        assert activo_id in ids_catalogo
        assert inactivo_id not in ids_catalogo

        admin = listar_espacios_admin()
        ids_admin = [e["id"] for e in admin]
        assert activo_id in ids_admin
        assert inactivo_id in ids_admin


def test_dias_semana_mapeo():
    assert DIAS_SEMANA[0] == "Lunes"
    assert DIAS_SEMANA[6] == "Domingo"
    assert len(DIAS_SEMANA) == 7


def test_dia_booleano_rechazado():
    with pytest.raises(ErrorFranjaHoraria):
        validar_lista_franjas([{"dia_semana": True, "abre": "09:00", "cierra": "12:00"}])


def test_dia_como_texto_de_formulario(app):
    with app.app_context():
        espacio_id = crear_espacio(nombre="Sala Texto")
        agregar_franja_horaria(espacio_id, "2", "09:00", "12:00")
        assert obtener_horarios_espacio(espacio_id)[0]["dia_semana"] == 2


def test_capacidad_como_texto_de_formulario(app):
    with app.app_context():
        espacio_id = crear_espacio(nombre="Sala Form", capacidad="20")
        assert obtener_espacio(espacio_id)["capacidad"] == 20


def test_capacidad_booleana_rechazada(app):
    with app.app_context(), pytest.raises(ErrorEspacio):
        crear_espacio(nombre="Sala Bool", capacidad=True)


def test_catalogo_sin_consulta_por_espacio(app, monkeypatch):
    llamadas = []
    original = db.query

    def contar(sql, **params):
        llamadas.append(sql)
        return original(sql, **params)

    monkeypatch.setattr(db, "query", contar)
    with app.app_context():
        espacios = listar_espacios_catalogo()
        listar_espacios_admin()
    assert len(espacios) > 2
    assert len(llamadas) == 4
    assert any(e["horarios"] for e in espacios)
