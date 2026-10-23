from davincihub import db
from davincihub.objetos import datos


def test_init_demo_desde_cli_incluye_publicaciones(app):
    resultado = app.test_cli_runner().invoke(args=["init-db", "--demo"])
    assert resultado.exit_code == 0
    with app.app_context():
        assert db.query_one("SELECT count(*) AS n FROM publicaciones")["n"] == 10


def test_cada_estudiante_demo_tiene_dos_publicaciones(app):
    with app.app_context():
        autores = db.query(
            "SELECT u.email, count(p.id) AS cantidad FROM usuarios u"
            " LEFT JOIN publicaciones p ON p.autor_id = u.id"
            " WHERE u.rol = 'estudiante' GROUP BY u.id, u.email"
        )
        assert len(autores) == 5
        assert all(a["cantidad"] == 2 for a in autores)
        publicaciones = db.query("SELECT p.*, u.carrera_id AS carrera_autor FROM publicaciones p"
                                 " JOIN usuarios u ON u.id = p.autor_id")
        assert all(p["carrera_id"] == p["carrera_autor"] for p in publicaciones)
        assert {p["categoria"] for p in publicaciones} == set(datos.CATEGORIAS)
        assert {p["modalidad"] for p in publicaciones} == set(datos.MODALIDADES)
        assert {p["estado_objeto"] for p in publicaciones} == set(datos.CONDICIONES)
        assert all(p["precio"] > 0 if p["modalidad"] == "venta" else p["precio"] is None
                   for p in publicaciones)


def test_segunda_carga_no_duplica_ni_reabre_publicaciones(app):
    with app.app_context():
        p = db.query_one("SELECT id FROM publicaciones ORDER BY id LIMIT 1")
        db.execute("UPDATE publicaciones SET estado = 'cerrada', precio = 123 WHERE id = :id", id=p["id"])
        assert db.cargar_publicaciones_demo() == 0
        assert db.query_one("SELECT count(*) AS n FROM publicaciones")["n"] == 10
        assert db.query_one("SELECT estado, precio FROM publicaciones WHERE id = :id", id=p["id"]) == {
            "estado": "cerrada", "precio": 123,
        }


def test_seed_no_modifica_publicaciones_propias_ni_otros_datos(app):
    with app.app_context():
        # Se simula una base existente con usuarios demo, sin sus ejemplos de objetos.
        db.execute("DELETE FROM publicaciones")
        propia = datos.crear(2, {
            "titulo": "Material propio", "descripcion": "No debe perderse.",
            "categoria": "otros", "estado_objeto": "nuevo_como_nuevo",
            "modalidad": "prestamo", "carrera_id": "",
        })
        db.execute("UPDATE publicaciones SET estado = 'pausada' WHERE id = :id", id=propia)
        antes = datos.obtener(propia)
        reservas = db.query("SELECT * FROM reservas ORDER BY id")
        usuarios = db.query("SELECT * FROM usuarios ORDER BY id")
    resultado = app.test_cli_runner().invoke(args=["seed-objetos"])
    assert resultado.exit_code == 0
    assert "agregadas: 10" in resultado.output
    with app.app_context():
        assert datos.obtener(propia) == antes
        assert db.query("SELECT * FROM reservas ORDER BY id") == reservas
        assert db.query("SELECT * FROM usuarios ORDER BY id") == usuarios


def test_seed_sin_cuentas_demo_no_inventa_usuarios(app):
    with app.app_context():
        db.init_db()
        assert db.cargar_publicaciones_demo() == 0
        assert db.query_one("SELECT count(*) AS n FROM usuarios")["n"] == 0


def test_ejemplos_del_bloqueado_no_aparecen_en_catalogo(app):
    with app.app_context():
        catalogo = datos.listar({})
        assert catalogo["total"] == 8
        assert len({p["autor_id"] for p in catalogo["publicaciones"]}) == 4
        bruno = db.query_one("SELECT id FROM usuarios WHERE email = 'bruno@davinci.edu.ar'")["id"]
        assert all(p["autor_id"] != bruno for p in catalogo["publicaciones"])
