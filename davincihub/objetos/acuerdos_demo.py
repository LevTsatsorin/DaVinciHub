"""Ejemplos aditivos para comprobar intercambios y ventas sin reiniciar la base."""

import click
from flask.cli import with_appcontext

from davincihub import db
from davincihub.objetos import acuerdos, datos

EJEMPLOS = [
    ("tomas", "mica", "Monitor de 24 pulgadas para trabajos de diseño", "venta", "computacion", "propuesto"),
    ("mica", "sofia", "Kit de pinceles y marcadores para ilustración", "intercambio", "dibujo_diseno", "propuesto"),
    ("mica", "tomas", "Micrófono USB para producciones audiovisuales", "venta", "audio_iluminacion", "aceptado"),
    ("lucia", "mica", "Manual de color y composición visual", "intercambio", "libros_apuntes", "confirmado"),
    ("sofia", "mica", "Mouse para edición y diseño", "venta", "computacion", "completado"),
    ("tomas", "mica", "Soporte de tableta para dibujar", "intercambio", "dibujo_diseno", "cancelado"),
]


def cargar():
    cantidad = 0
    with db.transaccion():
        for propietario, solicitante, titulo, tipo, categoria, estado in EJEMPLOS:
            usuarios = [db.query_one(
                "SELECT id FROM usuarios WHERE email = :email AND rol = 'estudiante' AND bloqueado = 0",
                email=f"{alias}@davinci.edu.ar",
            ) for alias in (propietario, solicitante)]
            if any(u is None for u in usuarios):
                continue
            dueno, quien = (u["id"] for u in usuarios)
            if db.query_one("SELECT id FROM publicaciones WHERE autor_id = :autor AND titulo = :titulo", autor=dueno, titulo=titulo):
                continue
            publicacion = datos.crear(dueno, {
                "titulo": titulo, "descripcion": "Material para la carrera en buen estado, con todos sus accesorios. Coordinamos la entrega en la escuela.",
                "categoria": categoria, "estado_objeto": "usado_buen_estado", "modalidad": tipo, "precio": "30000",
            })
            form = {"oferta": "Puedo retirarlo en la escuela. Ofrezco materiales de dibujo y un cuaderno de bocetos." if tipo == "intercambio" else "Podemos encontrarnos en la biblioteca para concretar la compra.",
                    "precio_acordado": "28000"}
            if estado == "confirmado":
                ofrecida = datos.crear(quien, {
                    "titulo": "Sketchbook A4 con papel para ilustración", "descripcion": "Cuaderno con hojas gruesas, casi sin uso. Lo cambio por material de lectura.",
                    "categoria": "dibujo_diseno", "estado_objeto": "nuevo_como_nuevo", "modalidad": "intercambio",
                })
                form["publicacion_ofrecida_id"] = str(ofrecida)
            t, aid = acuerdos.proponer(publicacion, quien, form)
            if estado == "aceptado":
                otra = db.query_one("SELECT id FROM usuarios WHERE email = 'sofia@davinci.edu.ar' AND bloqueado = 0")
                if otra:
                    acuerdos.proponer(publicacion, otra["id"], {"precio_acordado": "25000", "oferta": "Ofrezco $25.000 y retiro en la escuela."})
            if estado in ("aceptado", "confirmado", "completado"):
                acuerdos.cambiar(t, aid, dueno, "aceptar")
            if estado in ("confirmado", "completado"):
                acuerdos.cambiar(t, aid, quien, "confirmar")
            if estado == "completado":
                acuerdos.cambiar(t, aid, dueno, "confirmar")
            if estado == "cancelado":
                acuerdos.cambiar(t, aid, dueno, "rechazar")
            cantidad += 1
    return cantidad


@click.command("seed-acuerdos")
@with_appcontext
def comando_seed_acuerdos():
    """Agrega ejemplos C4 a los usuarios demo existentes sin borrar datos."""
    click.echo(f"Escenarios C4 agregados: {cargar()}. No se modificaron datos existentes.")
