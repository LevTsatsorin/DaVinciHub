import os

import pytest

from davincihub import comision, db
from davincihub.academico import datos as academico
from davincihub.app import create_app
from davincihub.demo_amplio import cargar

VIEJAS = {"mica@davinci.edu.ar": "A", "tomas@davinci.edu.ar": "TN", "lucia@davinci.edu.ar": None,
          "sofia@davinci.edu.ar": "comisión 3", "bruno@davinci.edu.ar": "ACT4AP"}


def _invalidas() -> list[dict]:
    carreras = {c["id"]: c for c in db.query("SELECT id, nombre, codigo, duracion_anios FROM carreras")}
    return [
        e for e in db.query("SELECT id, carrera_id, anio, comision FROM usuarios WHERE rol = 'estudiante'")
        if e["carrera_id"] and (comision.error(e["comision"], carreras[e["carrera_id"]])
                                or comision.anio(e["comision"]) != e["anio"])
    ]


def _base_vieja():
    """Deja la base como antes del formato: carreras sin código y comisiones sueltas."""
    db.execute("UPDATE carreras SET codigo = NULL")
    for email, valor in VIEJAS.items():
        db.execute("UPDATE usuarios SET comision = :c WHERE email = :e", c=valor, e=email)


def test_partes_anio_y_detalle():
    assert comision.partes(" act 4ap ") == {"carrera": "AC", "turno": "T", "cuatrimestre": 4,
                                            "division": "A", "modalidad": "P"}
    assert comision.anio("ACT4AP") == 2 and comision.anio("DMN5BV") == 3 and comision.anio("DMN12BV") == 6
    assert comision.detalle("ACT4AP") == "Turno tarde · 4.º cuatrimestre · división A · presencial"
    for invalida in ("A", "", None, "ACT4A", "ACX4AP", "ACT0AP", "ACT13AP", "ACT4AX", "AC T4AP!", "ÁCT4AP"):
        assert comision.partes(invalida) is None, invalida


def test_codigo_sugerido_respeta_los_usados():
    assert comision.codigo_sugerido("Analista de Sistemas", set()) == "AC"
    assert comision.codigo_sugerido("Analista de Sistemas", {"AC"}) == "AS"
    assert comision.codigo_sugerido("Ilustración Digital", set()) == "ID"
    assert comision.codigo_sugerido("Ilustración Digital", {"ID"}) not in {"ID"}
    assert comision.codigo_sugerido("¡¡", set()) == "AA"


def test_demo_completa_tiene_comisiones_validas(app):
    with app.app_context():
        cargar()
        assert _invalidas() == []
        assert db.query_one("SELECT count(*) AS n FROM carreras WHERE codigo IS NULL")["n"] == 0
        assert db.query_one("SELECT comision FROM usuarios WHERE email = 'nico@davinci.edu.ar'")["comision"] == "ACT6AP"


def test_al_arrancar_convierte_las_comisiones_viejas(app):
    with app.app_context():
        _base_vieja()
        assert _invalidas()
        db.migrar()
        assert _invalidas() == []
        codigos = {c["nombre"]: c["codigo"] for c in db.query("SELECT nombre, codigo FROM carreras")}
        assert codigos["Analista de Sistemas"] == "AC" and codigos["Diseño y Programación Web"] == "DW"
        filas = {f["email"]: f for f in db.query("SELECT email, anio, comision FROM usuarios WHERE rol = 'estudiante'")}
    mica, tomas = filas["mica@davinci.edu.ar"], filas["tomas@davinci.edu.ar"]
    assert mica["comision"][:2] == "DM" and mica["comision"][4:] == "AP" and mica["anio"] == 2
    assert tomas["comision"][:3] == "DVN" and tomas["anio"] == 1
    assert filas["lucia@davinci.edu.ar"]["anio"] == 3
    assert filas["bruno@davinci.edu.ar"]["comision"] == "DWT4AP" and filas["bruno@davinci.edu.ar"]["anio"] == 2


def test_la_conversion_no_repite_cambios(app):
    with app.app_context():
        _base_vieja()
        db.migrar()
        antes = db.query("SELECT id, anio, comision FROM usuarios ORDER BY id")
        db.migrar()
        assert db.query("SELECT id, anio, comision FROM usuarios ORDER BY id") == antes


def test_codigos_duplicados_se_corrigen_y_quedan_unicos(app):
    with app.app_context():
        db.execute("DROP INDEX idx_carreras_codigo")
        db.execute("UPDATE carreras SET codigo = 'DM' WHERE nombre = 'Diseño Gráfico'")
        db.migrar()
        codigos = [c["codigo"] for c in db.query("SELECT codigo FROM carreras")]
        assert len(codigos) == len(set(codigos))
        assert _invalidas() == []
        with pytest.raises(db.ErrorIntegridad):
            db.execute("UPDATE carreras SET codigo = 'DM' WHERE nombre = 'Diseño Gráfico'")


def _admin(client):
    client.post("/auth/login", data={"email": "admin@davinci.edu.ar", "password": "davinci123"})


def _mica(client):
    client.post("/auth/login", data={"email": "mica@davinci.edu.ar", "password": "davinci123"})


def test_admin_cambia_el_codigo_y_se_actualizan_las_comisiones(client, app):
    _admin(client)
    respuesta = client.post("/admin/carreras/1/editar",
                            data={"nombre": "Diseño Multimedial", "duracion_anios": "3", "codigo": "mu"})
    assert respuesta.status_code == 302
    with app.app_context():
        assert db.query_one("SELECT comision FROM usuarios WHERE email = 'mica@davinci.edu.ar'")["comision"] == "MUT4AP"
        assert _invalidas() == []
    assert "Comisiones MU" in client.get("/admin/carreras/").get_data(as_text=True)


def test_dejar_el_codigo_vacio_al_editar_lo_conserva(client, app):
    _admin(client)
    client.post("/admin/carreras/1/editar", data={"nombre": "Diseño Multimedial", "duracion_anios": "3"})
    with app.app_context():
        assert db.query_one("SELECT codigo FROM carreras WHERE id = 1")["codigo"] == "DM"


@pytest.mark.parametrize("codigo, mensaje", [("A1", "dos letras"), ("ABC", "dos letras"), ("DW", "ya es de")])
def test_admin_no_acepta_codigos_invalidos_ni_repetidos(client, app, codigo, mensaje):
    _admin(client)
    respuesta = client.post("/admin/carreras/1/editar",
                            data={"nombre": "Diseño Multimedial", "duracion_anios": "3", "codigo": codigo})
    assert mensaje in respuesta.get_data(as_text=True)
    with app.app_context():
        assert db.query_one("SELECT codigo FROM carreras WHERE id = 1")["codigo"] == "DM"


def test_carrera_nueva_sin_codigo_recibe_uno(client, app):
    _admin(client)
    client.post("/admin/carreras/nueva", data={"nombre": "Ilustración Digital", "duracion_anios": "2"})
    with app.app_context():
        assert db.query_one("SELECT codigo FROM carreras WHERE nombre = 'Ilustración Digital'")["codigo"] == "ID"


def test_no_se_acorta_una_carrera_con_estudiantes_en_anios_posteriores(app):
    with app.app_context():
        carrera_id = academico.guardar_carrera({"nombre": "Ilustración", "duracion_anios": "3", "codigo": "IL"})
        db.execute("UPDATE usuarios SET carrera_id = :c, anio = 3, comision = 'ILT5AP' WHERE id = 2", c=carrera_id)
        with pytest.raises(academico.ErrorAcademico, match="estudiantes en 3.º año"):
            academico.guardar_carrera({"nombre": "Ilustración", "duracion_anios": "2"}, carrera_id)
        assert academico.obtener_carrera(carrera_id)["duracion_anios"] == 3


def test_el_perfil_valida_la_comision_contra_la_carrera(client, app):
    _mica(client)
    datos = {"nombre": "Mica", "apellido": "Suárez", "carrera_id": "1"}
    respuesta = client.post("/estudiantes/2/editar", data=datos | {"comision": "DWT2AP"})
    assert "empiezan con DM" in respuesta.get_data(as_text=True)
    respuesta = client.post("/estudiantes/2/editar", data=datos | {"comision": ""})
    assert "Campo obligatorio" in respuesta.get_data(as_text=True)
    with app.app_context():
        assert db.query_one("SELECT comision FROM usuarios WHERE id = 2")["comision"] == "DMT4AP"
    perfil = client.get("/estudiantes/2").get_data(as_text=True)
    assert '<abbr title="Turno tarde · 4.º cuatrimestre · división A · presencial">DMT4AP</abbr>' in perfil


def test_la_busqueda_por_comision_acepta_prefijos_y_no_comodines(client):
    _mica(client)
    assert "Lucía Paz" in client.get("/estudiantes/buscar?comision=dm").get_data(as_text=True)
    assert "Lucía Paz" in client.get("/estudiantes/buscar?comision=DMN6AP").get_data(as_text=True)
    assert "Lucía Paz" not in client.get("/estudiantes/buscar?comision=DMT").get_data(as_text=True)
    assert "Lucía Paz" not in client.get("/estudiantes/buscar?comision=%25N6").get_data(as_text=True)


def test_postgres_convierte_comisiones_viejas():
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("sin TEST_DATABASE_URL")
    aplicacion = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "DATABASE_URL": url})
    with aplicacion.app_context():
        db.init_db(demo=True)  # Únicamente una base de pruebas desechable.
        cargar()
        _base_vieja()
        db.migrar()
        assert _invalidas() == []
        db.migrar()
        assert _invalidas() == []
    cliente = aplicacion.test_client()
    _mica(cliente)
    assert "Lucía Paz" in cliente.get("/estudiantes/buscar?comision=dm").get_data(as_text=True)
    assert "Lucía Paz" not in cliente.get("/estudiantes/buscar?comision=dw").get_data(as_text=True)
