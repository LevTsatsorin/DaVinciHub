"""Préstamos de materiales entre estudiantes (C3 / RF-16)."""

from datetime import date

import click
from flask import g, request
from flask.cli import with_appcontext

from davincihub import db
from davincihub.notificaciones import notificar
from davincihub.objetos import datos
from davincihub.utiles import ahora, hoy_local

ESTADOS = {
    "pendiente": "Pendiente", "aceptado": "Aceptado", "en_prestamo": "En préstamo",
    "devuelto": "Devuelto", "vencido": "Vencido", "cancelado": "Cancelado",
}
OCUPADOS = ("aceptado", "en_prestamo", "vencido")


class ErrorPrestamo(datos.ErrorPublicacion):
    pass


def _error(texto):
    raise ErrorPrestamo({"general": texto})


def _fechas(form):
    campos, errores = {}, {}
    for campo in ("fecha_entrega", "fecha_devolucion"):
        texto = (form.get(campo) or "").strip()
        try:
            valor = date.fromisoformat(texto)
            if valor.isoformat() != texto:
                raise ValueError
            campos[campo] = texto
        except ValueError:
            errores[campo] = "Ingresá una fecha válida."
    if "fecha_entrega" in campos and campos["fecha_entrega"] < hoy_local():
        errores["fecha_entrega"] = "La entrega debe ser hoy o una fecha futura."
    if len(campos) == 2 and campos["fecha_devolucion"] < campos["fecha_entrega"]:
        errores["fecha_devolucion"] = "La devolución no puede ser anterior a la entrega."
    if errores:
        raise ErrorPrestamo(errores)
    return campos


def _texto(form, campo, obligatorio=False):
    valor = (form.get(campo) or "").strip()
    if obligatorio and not valor:
        raise ErrorPrestamo({campo: "Indicá las condiciones del préstamo."})
    if len(valor) > 2000:
        raise ErrorPrestamo({campo: "Usá como máximo 2000 caracteres."})
    return valor


def obtener(prestamo_id):
    return db.query_one(
        "SELECT pr.*, p.autor_id AS propietario_id, p.titulo, p.categoria,"
        " p.modalidad, p.estado AS estado_publicacion, p.oculto,"
        " du.nombre AS propietario_nombre, du.apellido AS propietario_apellido,"
        " du.bloqueado AS propietario_bloqueado,"
        " so.nombre AS solicitante_nombre, so.apellido AS solicitante_apellido,"
        " so.bloqueado AS solicitante_bloqueado"
        " FROM prestamos pr JOIN publicaciones p ON p.id = pr.publicacion_id"
        " JOIN usuarios du ON du.id = p.autor_id JOIN usuarios so ON so.id = pr.solicitante_id"
        " WHERE pr.id = :id", id=prestamo_id,
    )


def ocupado(publicacion_id, excepto=None):
    # No enviar un NULL sin tipo a PostgreSQL ("param IS NULL" falla al preparar).
    exclusion = " AND id <> :excepto" if excepto is not None else ""
    params = {"publicacion": publicacion_id}
    if excepto is not None:
        params["excepto"] = excepto
    return db.query_one(
        "SELECT id FROM prestamos WHERE publicacion_id = :publicacion"
        " AND estado IN ('aceptado', 'en_prestamo', 'vencido')"
        + exclusion + " LIMIT 1",
        **params,
    ) is not None


def pendiente_propio(publicacion_id, usuario_id):
    return db.query_one(
        "SELECT id FROM prestamos WHERE publicacion_id = :publicacion"
        " AND solicitante_id = :usuario AND estado IN ('pendiente', 'aceptado', 'en_prestamo', 'vencido')"
        " ORDER BY id DESC LIMIT 1", publicacion=publicacion_id, usuario=usuario_id,
    )


def _movimiento(prestamo_id, anterior, nuevo, actor, detalle=""):
    db.execute(
        "INSERT INTO prestamos_movimientos (prestamo_id, estado_anterior, estado_nuevo,"
        " actor_id, detalle, creado) VALUES (:prestamo, :anterior, :nuevo, :actor, :detalle, :creado)",
        prestamo=prestamo_id, anterior=anterior, nuevo=nuevo, actor=actor,
        detalle=detalle, creado=ahora(),
    )


def _aviso(usuario_id, prestamo_id, texto):
    notificar(usuario_id, "objetos", texto, f"/objetos/prestamos/{prestamo_id}")


def solicitar(publicacion_id, usuario_id, form):
    datos._estudiante(usuario_id)
    fechas = _fechas(form)
    mensaje = _texto(form, "mensaje")
    with db.transaccion():
        if not db.bloquear_fila("publicaciones", publicacion_id):
            raise LookupError("No existe la publicación.")
        publicacion = datos.obtener(publicacion_id)
        if publicacion["autor_id"] == usuario_id:
            _error("No podés pedir prestado un objeto propio.")
        if (publicacion["estado"] != "activa" or publicacion["oculto"]
                or publicacion["autor_bloqueado"] or publicacion["modalidad"] != "prestamo"):
            _error("Esta publicación no está disponible para préstamo.")
        if ocupado(publicacion_id):
            _error("Este objeto ya tiene un préstamo en curso. Esperá a que se registre su devolución.")
        if pendiente_propio(publicacion_id, usuario_id):
            _error("Ya tenés una solicitud abierta para este objeto.")
        fila = db.query_one(
            "INSERT INTO prestamos (publicacion_id, solicitante_id, fecha_entrega, fecha_devolucion,"
            " mensaje, creado) VALUES (:publicacion, :solicitante, :fecha_entrega, :fecha_devolucion,"
            " :mensaje, :creado) RETURNING id", publicacion=publicacion_id, solicitante=usuario_id,
            mensaje=mensaje, creado=ahora(), **fechas,
        )
        _movimiento(fila["id"], None, "pendiente", usuario_id, mensaje)
        _aviso(publicacion["autor_id"], fila["id"],
               f'Nuevo pedido de préstamo para «{publicacion["titulo"]}».')
    return fila["id"]


def acciones(pr, usuario_id):
    propietario = pr["propietario_id"] == usuario_id
    if pr["estado"] == "pendiente":
        return ["aceptar", "rechazar"] if propietario else ["cancelar"]
    if pr["estado"] == "aceptado":
        return ["entregar", "cancelar"] if propietario else ["cancelar"]
    if pr["estado"] in ("en_prestamo", "vencido") and propietario:
        return ["devolver"]
    return []


def cambiar(prestamo_id, usuario_id, accion, form=None):
    datos._estudiante(usuario_id)
    form = form or {}
    previo = obtener(prestamo_id)
    if previo is None:
        raise LookupError("No existe el préstamo.")
    if usuario_id not in (previo["propietario_id"], previo["solicitante_id"]):
        raise PermissionError("Este préstamo no te pertenece.")
    with db.transaccion():
        # Siempre publicación antes que préstamo: serializa reservas del mismo objeto.
        db.bloquear_fila("publicaciones", previo["publicacion_id"])
        db.bloquear_fila("prestamos", prestamo_id)
        pr = obtener(prestamo_id)
        if accion not in acciones(pr, usuario_id):
            _error("Esta acción no está permitida en el estado actual del préstamo.")
        if accion == "aceptar":
            if (pr["modalidad"] != "prestamo" or pr["estado_publicacion"] != "activa"
                    or pr["oculto"] or pr["solicitante_bloqueado"]):
                _error("La publicación o el solicitante ya no están disponibles.")
            if ocupado(pr["publicacion_id"], excepto=prestamo_id):
                _error("El objeto ya tiene otro préstamo en curso.")
            campos = _fechas(form)
            condiciones = _texto(form, "condiciones", obligatorio=True)
            db.execute(
                "UPDATE prestamos SET fecha_entrega = :fecha_entrega, fecha_devolucion = :fecha_devolucion,"
                " condiciones = :condiciones WHERE id = :id", id=prestamo_id,
                condiciones=condiciones, **campos,
            )
            nuevo, detalle = "aceptado", condiciones
            destinatarios = [pr["solicitante_id"]]
            texto = f'Tu pedido de préstamo de «{pr["titulo"]}» fue aceptado. Revisá las condiciones y fechas.'
        elif accion == "entregar":
            if not pr["fecha_entrega"] <= hoy_local() <= pr["fecha_devolucion"]:
                _error("La entrega debe registrarse entre las fechas acordadas.")
            if pr["solicitante_bloqueado"]:
                _error("No se puede entregar el objeto a un usuario bloqueado. Cancelá el préstamo.")
            db.execute("UPDATE prestamos SET entregado = :fecha WHERE id = :id", fecha=ahora(), id=prestamo_id)
            nuevo, detalle = "en_prestamo", "El propietario registró la entrega del objeto."
            destinatarios = [pr["solicitante_id"]]
            texto = f'Se registró la entrega de «{pr["titulo"]}». Recordá la fecha de devolución.'
        elif accion == "devolver":
            if not pr["entregado"]:
                _error("No se puede registrar una devolución sin una entrega previa.")
            db.execute("UPDATE prestamos SET devuelto = :fecha WHERE id = :id", fecha=ahora(), id=prestamo_id)
            nuevo, detalle = "devuelto", "El propietario confirmó que recibió el objeto."
            destinatarios = [pr["solicitante_id"]]
            texto = f'Se confirmó la devolución de «{pr["titulo"]}». ¡Préstamo finalizado!'
        else:
            nuevo = "cancelado"
            detalle = "Solicitud rechazada por el propietario." if accion == "rechazar" else "Préstamo cancelado antes de la entrega."
            db.execute("UPDATE prestamos SET motivo_cierre = :motivo WHERE id = :id", motivo=detalle, id=prestamo_id)
            destinatarios = [pr["solicitante_id"] if usuario_id == pr["propietario_id"] else pr["propietario_id"]]
            texto = f'El pedido de préstamo de «{pr["titulo"]}» fue ' + ("rechazado." if accion == "rechazar" else "cancelado.")
        db.execute("UPDATE prestamos SET estado = :estado WHERE id = :id", estado=nuevo, id=prestamo_id)
        _movimiento(prestamo_id, pr["estado"], nuevo, usuario_id, detalle)
        for destinatario in destinatarios:
            _aviso(destinatario, prestamo_id, texto)


def actualizar_vencidos():
    candidatos = db.query(
        "SELECT id, publicacion_id FROM prestamos WHERE estado = 'en_prestamo'"
        " AND fecha_devolucion < :hoy ORDER BY publicacion_id, id", hoy=hoy_local(),
    )
    cantidad = 0
    for candidato in candidatos:
        with db.transaccion():
            db.bloquear_fila("publicaciones", candidato["publicacion_id"])
            db.bloquear_fila("prestamos", candidato["id"])
            pr = obtener(candidato["id"])
            if pr is None or pr["estado"] != "en_prestamo" or pr["fecha_devolucion"] >= hoy_local():
                continue
            db.execute("UPDATE prestamos SET estado = 'vencido' WHERE id = :id", id=pr["id"])
            _movimiento(pr["id"], "en_prestamo", "vencido", None, "Pasó la fecha de devolución acordada.")
            for usuario in (pr["propietario_id"], pr["solicitante_id"]):
                _aviso(usuario, pr["id"], f'El préstamo de «{pr["titulo"]}» está vencido. Coordiná la devolución.')
            cantidad += 1
    return cantidad


def revisar_vencidos():
    if g.get("usuario") and request.endpoint and request.endpoint != "static":
        actualizar_vencidos()


def movimientos(prestamo_id):
    return db.query(
        "SELECT m.*, u.nombre, u.apellido FROM prestamos_movimientos m"
        " LEFT JOIN usuarios u ON u.id = m.actor_id WHERE m.prestamo_id = :id ORDER BY m.id",
        id=prestamo_id,
    )


def listar(usuario_id, vista="pedidos", estado="", pagina=1):
    vista = vista if vista in ("pedidos", "otorgados") else "pedidos"
    estado = estado if estado in ESTADOS else ""
    condicion = "pr.solicitante_id = :usuario" if vista == "pedidos" else "p.autor_id = :usuario"
    if estado:
        condicion += " AND pr.estado = :estado"
    params = {"usuario": usuario_id, **({"estado": estado} if estado else {})}
    tablas = " FROM prestamos pr JOIN publicaciones p ON p.id = pr.publicacion_id WHERE " + condicion
    total = db.query_one("SELECT count(*) AS n" + tablas, **params)["n"]
    paginas = max(1, (total + datos.POR_PAGINA - 1) // datos.POR_PAGINA)
    pagina = min(max(1, pagina), paginas)
    filas = db.query("SELECT pr.id" + tablas + " ORDER BY pr.creado DESC, pr.id DESC LIMIT :limite OFFSET :salto",
                     limite=datos.POR_PAGINA, salto=(pagina - 1) * datos.POR_PAGINA, **params)
    return {"prestamos": [obtener(f["id"]) for f in filas], "total": total, "pagina": pagina,
            "paginas": paginas, "vista": vista, "estado": estado}


@click.command("marcar-prestamos-vencidos")
@with_appcontext
def marcar_vencidos_command():
    click.echo(f"Préstamos vencidos actualizados: {actualizar_vencidos()}.")
