"""Ejemplos C3 aditivos: no reinician la base ni alteran publicaciones existentes."""

from datetime import date, datetime, time, timedelta

import click
from flask.cli import with_appcontext

from davincihub import db
from davincihub.objetos import datos, prestamos
from davincihub.utiles import ZONA_LOCAL, ahora, hoy_local

# propietario, solicitante, título, categoría, estado
EJEMPLOS = [
    ("mica", "tomas", "Trípode liviano para rodajes estudiantiles", "foto_video", "pendiente"),
    ("tomas", "mica", "Grabador portátil para entrevistas", "audio_iluminacion", "aceptado"),
    ("lucia", "mica", "Tableta gráfica para prácticas de ilustración", "dibujo_diseno", "en_prestamo"),
    ("mica", "sofia", "Kit de luces LED para un cortometraje", "audio_iluminacion", "vencido"),
    ("mica", "tomas", "Manual de narrativa audiovisual para consultar", "libros_apuntes", "devuelto"),
    ("sofia", "mica", "Calculadora científica para rendir matemática", "utiles", "cancelado"),
]


def cargar():
    cantidad = 0
    hoy = date.fromisoformat(hoy_local())

    def momento(dia, hora=10):
        return datetime.combine(dia, time(hora), tzinfo=ZONA_LOCAL).isoformat(timespec="seconds")

    with db.transaccion():
        for propietario, solicitante, titulo, categoria, estado in EJEMPLOS:
            usuarios = []
            for alias in (propietario, solicitante):
                usuarios.append(db.query_one(
                    "SELECT id FROM usuarios WHERE email = :email AND rol = 'estudiante' AND bloqueado = 0",
                    email=f"{alias}@davinci.edu.ar",
                ))
            if any(u is None for u in usuarios):
                continue
            dueno, quien = (u["id"] for u in usuarios)
            # Un ejemplo ya existente se conserva, aun si el préstamo fue devuelto o cancelado.
            existente = db.query_one(
                "SELECT id FROM publicaciones WHERE autor_id = :autor AND titulo = :titulo",
                autor=dueno, titulo=titulo,
            )
            if existente:
                continue
            publicacion = datos.crear(dueno, {
                "titulo": titulo, "descripcion": "Material de estudio disponible para compartir. Se entrega con sus accesorios y se devuelve en las mismas condiciones.",
                "categoria": categoria, "estado_objeto": "usado_buen_estado", "modalidad": "prestamo",
            })
            historico = estado in ("en_prestamo", "vencido", "devuelto")
            entrega = hoy - timedelta(days=5) if historico else hoy
            devolucion = hoy - timedelta(days=2) if estado in ("vencido", "devuelto") else hoy + timedelta(days=4)
            creado = momento(entrega - timedelta(days=1))
            entregado = momento(entrega) if historico else None
            devuelto = momento(devolucion) if estado == "devuelto" else None
            condiciones = "Retirar en la biblioteca con todos los accesorios. Devolver en el mismo lugar, limpio y funcionando." if estado not in ("pendiente", "cancelado") else None
            motivo = "Solicitud rechazada por el propietario." if estado == "cancelado" else ""
            fila = db.query_one(
                "INSERT INTO prestamos (publicacion_id, solicitante_id, estado, fecha_entrega,"
                " fecha_devolucion, condiciones, mensaje, motivo_cierre, entregado, devuelto, creado)"
                " VALUES (:publicacion, :solicitante, :estado, :entrega, :devolucion, :condiciones,"
                " :mensaje, :motivo, :entregado, :devuelto, :creado) RETURNING id",
                publicacion=publicacion, solicitante=quien, estado=estado,
                entrega=entrega.isoformat(), devolucion=devolucion.isoformat(), condiciones=condiciones,
                mensaje="Lo necesito para una entrega de la carrera. Puedo retirarlo en la escuela.",
                motivo=motivo, entregado=entregado, devuelto=devuelto, creado=creado,
            )
            pasos = [(None, "pendiente", quien, "Solicitud enviada.", creado)]
            if estado not in ("pendiente", "cancelado"):
                pasos.append(("pendiente", "aceptado", dueno, condiciones, momento(entrega - timedelta(days=1), 12)))
            if historico:
                pasos.append(("aceptado", "en_prestamo", dueno, "El propietario registró la entrega del objeto.", entregado))
            if estado == "devuelto":
                pasos.append(("en_prestamo", "devuelto", dueno, "El propietario confirmó que recibió el objeto.", devuelto))
            if estado == "vencido":
                pasos.append(("en_prestamo", "vencido", None, "Pasó la fecha de devolución acordada.", momento(devolucion + timedelta(days=1))))
            if estado == "cancelado":
                pasos.append(("pendiente", "cancelado", dueno, motivo, ahora()))
            for anterior, nuevo, actor, detalle, fecha in pasos:
                db.execute(
                    "INSERT INTO prestamos_movimientos (prestamo_id, estado_anterior, estado_nuevo, actor_id, detalle, creado)"
                    " VALUES (:prestamo, :anterior, :nuevo, :actor, :detalle, :creado)", prestamo=fila["id"],
                    anterior=anterior, nuevo=nuevo, actor=actor, detalle=detalle, creado=fecha,
                )
            if estado == "pendiente":
                prestamos._aviso(dueno, fila["id"], f'Nuevo pedido de préstamo para «{titulo}».')
            elif estado == "vencido":
                for usuario in (dueno, quien):
                    prestamos._aviso(usuario, fila["id"], f'El préstamo de «{titulo}» está vencido. Coordiná la devolución.')
            else:
                prestamos._aviso(quien, fila["id"], f'Préstamo de «{titulo}»: {prestamos.ESTADOS[estado].lower()}.')
            cantidad += 1
    return cantidad


@click.command("seed-prestamos")
@with_appcontext
def comando_seed_prestamos():
    """Agrega ejemplos C3 a los usuarios demo existentes sin borrar sus datos."""
    click.echo(f"Préstamos demo agregados: {cargar()}. No se modificaron datos existentes.")
