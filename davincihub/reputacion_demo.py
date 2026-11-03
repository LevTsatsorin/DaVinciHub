"""Ejemplos aditivos para ver reputación e insignias sin reiniciar la base."""

import click
from flask.cli import with_appcontext

from davincihub import db

COMENTARIOS = {
    5: "Todo impecable y súper puntual. Lo recomiendo.",
    4: "Muy buena onda, tardamos un poco en coordinar pero salió bien.",
    3: "Cumplió, aunque costó encontrar un horario.",
}
# receptor, autores de cada opinión, puntajes
EJEMPLOS = {
    "mica": (("tomas", "sofia", "lucia"), (5, 5, 4, 5, 5, 5, 4, 5, 5, 5)),
    "tomas": (("mica", "sofia", "lucia"), (5, 4, 4, 4, 5, 4)),
    "lucia": (("mica", "tomas", "sofia"), (4, 3, 5)),
}
MATERIALES = (
    ("Set de escuadras y reglas", "dibujo_diseno"),
    ("Apuntes de historia del arte", "libros_apuntes"),
    ("Auriculares para edición", "audio_iluminacion"),
    ("Mochila para cámara", "foto_video"),
)


def _id(alias):
    fila = db.query_one(
        "SELECT id FROM usuarios WHERE email = :email AND rol = 'estudiante' AND bloqueado = 0",
        email=f"{alias}@davinci.edu.ar",
    )
    return fila["id"] if fila else None


def _operacion(modalidad, publicacion, quien, creado):
    if modalidad == "venta":
        return db.query_one(
            "INSERT INTO ventas (publicacion_id, comprador_id, precio_acordado, estado,"
            " confirmado_propietario, confirmado_solicitante, completado, creado)"
            " VALUES (:p, :q, 20000, 'completada', 1, 1, :c, :c) RETURNING id",
            p=publicacion, q=quien, c=creado,
        )["id"]
    if modalidad == "intercambio":
        return db.query_one(
            "INSERT INTO intercambios (publicacion_id, solicitante_id, oferta, estado,"
            " confirmado_propietario, confirmado_solicitante, completado, creado)"
            " VALUES (:p, :q, 'Materiales de dibujo', 'completado', 1, 1, :c, :c) RETURNING id",
            p=publicacion, q=quien, c=creado,
        )["id"]
    return db.query_one(
        "INSERT INTO prestamos (publicacion_id, solicitante_id, estado, fecha_entrega, fecha_devolucion,"
        " entregado, devuelto, creado) VALUES (:p, :q, 'devuelto', :d, :d, :c, :c, :c) RETURNING id",
        p=publicacion, q=quien, d=creado[:10], c=creado,
    )["id"]


def cargar():
    cantidad = 0
    modalidades = ("venta", "prestamo", "intercambio")
    with db.transaccion():
        for alias, (autores, puntajes) in EJEMPLOS.items():
            receptor = _id(alias)
            ids = [_id(a) for a in autores]
            if receptor is None or None in ids:
                continue
            for i, valor in enumerate(puntajes):
                titulo, categoria = MATERIALES[i % len(MATERIALES)]
                titulo = f"{titulo} ({i + 1})"
                if db.query_one("SELECT id FROM publicaciones WHERE autor_id = :a AND titulo = :t", a=receptor, t=titulo):
                    continue
                modalidad = modalidades[i % len(modalidades)]
                creado = f"2026-10-{1 + i:02d}T15:00:00+00:00"
                publicacion = db.query_one(
                    "INSERT INTO publicaciones (autor_id, titulo, descripcion, categoria, estado_objeto,"
                    " modalidad, precio, estado, creado) VALUES (:a, :t, :d, :cat, 'usado_buen_estado',"
                    " :m, :precio, 'cerrada', :c) RETURNING id",
                    a=receptor, t=titulo, d="Material en buen estado, ya entregado.", cat=categoria,
                    m=modalidad, precio=20000 if modalidad == "venta" else None, c=creado,
                )["id"]
                autor = ids[i % len(ids)]
                db.execute(
                    "INSERT INTO valoraciones_operaciones (tipo_operacion, operacion_id, autor_id, receptor_id,"
                    " valor, comentario, creado) VALUES (:tipo, :op, :autor, :receptor, :valor, :comentario, :c)",
                    tipo=modalidad, op=_operacion(modalidad, publicacion, autor, creado), autor=autor,
                    receptor=receptor, valor=valor, comentario=COMENTARIOS[valor], c=creado,
                )
                cantidad += 1
    return cantidad


@click.command("seed-reputacion")
@with_appcontext
def comando_seed_reputacion():
    """Agrega operaciones finalizadas con opiniones a los usuarios demo sin borrar datos."""
    click.echo(f"Opiniones demo agregadas: {cargar()}. No se modificaron datos existentes.")
