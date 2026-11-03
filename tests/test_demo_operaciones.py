from davincihub import db, demo_operaciones
from davincihub.demo_amplio import cargar as cargar_amplio
from davincihub.objetos import historial


def _preparar():
    db.init_db(demo=True)
    cargar_amplio()


def test_cubre_todos_los_estados_de_cada_tipo(app):
    with app.app_context():
        _preparar()
        demo_operaciones.cargar()
        for tabla, esperados in (
            ("prestamos", {"pendiente", "aceptado", "en_prestamo", "devuelto", "vencido", "cancelado"}),
            ("intercambios", {"propuesto", "aceptado", "completado", "cancelado"}),
            ("ventas", {"propuesta", "aceptada", "completada", "cancelada"}),
        ):
            filas = db.query(f"SELECT DISTINCT estado FROM {tabla}")
            assert {f["estado"] for f in filas} == esperados


def test_cada_estudiante_activo_tiene_historial_con_operaciones(app):
    with app.app_context():
        _preparar()
        demo_operaciones.cargar()
        alumnos = db.query("SELECT id, email FROM usuarios WHERE rol = 'estudiante' AND bloqueado = 0")
        sin_operaciones = [
            a["email"] for a in alumnos
            if sum(n for t, n in historial.cantidades(a["id"]).items() if t != "publicacion") == 0
        ]
        assert sin_operaciones == []
        assert not db.query(
            "SELECT id FROM usuarios WHERE rol = 'estudiante' AND bloqueado = 0"
            " AND id NOT IN (SELECT usuario_id FROM reservas)"
        )
        assert not db.query(
            "SELECT id FROM usuarios WHERE rol = 'estudiante' AND bloqueado = 0"
            " AND id NOT IN (SELECT autor_id FROM solicitudes)"
        )


def test_es_repetible_y_no_toca_lo_existente(app):
    with app.app_context():
        _preparar()
        previas = db.query_one("SELECT count(*) AS n FROM publicaciones WHERE estado = 'activa'")["n"]
        titulo = db.query_one("SELECT id, titulo, estado FROM publicaciones ORDER BY id")
        assert sum(demo_operaciones.cargar().values()) > 0
        conteos = [db.query_one(f"SELECT count(*) AS n FROM {t}")["n"]
                   for t in ("prestamos", "ventas", "intercambios", "valoraciones_operaciones", "reservas", "solicitudes")]
        assert sum(demo_operaciones.cargar().values()) == 0
        assert conteos == [db.query_one(f"SELECT count(*) AS n FROM {t}")["n"]
                           for t in ("prestamos", "ventas", "intercambios", "valoraciones_operaciones", "reservas", "solicitudes")]
        assert db.query_one("SELECT titulo, estado FROM publicaciones WHERE id = :id", id=titulo["id"])["estado"] == titulo["estado"]
        assert db.query_one("SELECT count(*) AS n FROM publicaciones WHERE estado = 'activa'")["n"] >= previas


def test_coherencia_de_estados_y_valoraciones(app):
    with app.app_context():
        _preparar()
        demo_operaciones.cargar()
        assert not db.query(
            "SELECT v.id FROM ventas v JOIN publicaciones p ON p.id = v.publicacion_id"
            " WHERE v.estado = 'completada' AND p.estado <> 'cerrada'"
        )
        assert not db.query(
            "SELECT o.id FROM valoraciones_operaciones o JOIN prestamos p ON p.id = o.operacion_id"
            " WHERE o.tipo_operacion = 'prestamo' AND p.estado <> 'devuelto'"
        )
        assert not db.query(
            "SELECT pr.id FROM prestamos pr JOIN publicaciones p ON p.id = pr.publicacion_id"
            " WHERE p.autor_id = pr.solicitante_id"
        )
        bloqueado = db.query_one("SELECT id FROM usuarios WHERE email = 'ramiro@davinci.edu.ar'")["id"]
        assert not db.query("SELECT id FROM reservas WHERE usuario_id = :u AND motivo LIKE 'Práctica%'", u=bloqueado)
        sin_cancelar = db.query("SELECT id FROM prestamos WHERE estado = 'aceptado' AND fecha_devolucion < :hoy", hoy="2026-01-01")
        assert sin_cancelar == []


def test_pantallas_con_datos_sembrados(app, client):
    with app.app_context():
        _preparar()
        demo_operaciones.cargar()
        alumno = db.query_one("SELECT id FROM usuarios WHERE email = 'valen@davinci.edu.ar'")["id"]
    with client.session_transaction() as sesion:
        sesion["usuario_id"] = alumno
    for ruta in ("/objetos/historial", "/objetos/prestamos", "/objetos/acuerdos", "/objetos/mis-busquedas", "/reservas/mias"):
        assert client.get(ruta).status_code in (200, 404), ruta
    assert client.get("/objetos/historial").status_code == 200
