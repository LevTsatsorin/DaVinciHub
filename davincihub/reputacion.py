"""RF-24: reputación calculada sobre operaciones finalizadas."""
from flask import Blueprint, abort, flash, g, redirect, request, url_for

from davincihub import db, seguridad
from davincihub.objetos import acuerdos, datos, prestamos
from davincihub.utiles import ahora

bp = Blueprint("reputacion", __name__, url_prefix="/reputacion")
TABLAS = {"prestamo": "prestamos", "intercambio": "intercambios", "venta": "ventas"}


def propia(tipo, operacion_id, autor_id):
    return db.query_one(
        "SELECT valor, comentario FROM valoraciones_operaciones"
        " WHERE tipo_operacion = :tipo AND operacion_id = :op AND autor_id = :autor",
        tipo=tipo, op=operacion_id, autor=autor_id,
    )


def valorar(tipo, operacion_id, autor_id, form):
    datos._estudiante(autor_id)
    if tipo not in TABLAS:
        raise LookupError
    with db.transaccion():
        if not db.bloquear_fila(TABLAS[tipo], operacion_id):
            raise LookupError
        op = prestamos.obtener(operacion_id) if tipo == "prestamo" else acuerdos.obtener(tipo, operacion_id)
        participantes = (op["propietario_id"], op["solicitante_id"])
        if autor_id not in participantes or participantes[0] == participantes[1]:
            raise PermissionError
        if op["estado"] != ("devuelto" if tipo == "prestamo" else "completado"):
            raise ValueError("Sólo podés valorar una operación finalizada.")
        if propia(tipo, operacion_id, autor_id):
            raise ValueError("Ya valoraste esta operación.")
        valor = form.get("valor", "")
        if valor not in ("1", "2", "3", "4", "5"):
            raise ValueError("Elegí una puntuación de 1 a 5.")
        comentario = (form.get("comentario") or "").strip()
        if len(comentario) > 2000:
            raise ValueError("El comentario puede tener hasta 2000 caracteres.")
        receptor = participantes[1] if autor_id == participantes[0] else participantes[0]
        db.execute(
            "INSERT INTO valoraciones_operaciones"
            " (tipo_operacion, operacion_id, autor_id, receptor_id, valor, comentario, creado)"
            " VALUES (:tipo, :op, :autor, :receptor, :valor, :comentario, :creado)",
            tipo=tipo, op=operacion_id, autor=autor_id, receptor=receptor,
            valor=int(valor), comentario=comentario, creado=ahora(),
        )


@bp.post("/<tipo>/<int:operacion_id>")
@seguridad.requiere_login
def crear(tipo, operacion_id):
    try:
        valorar(tipo, operacion_id, g.usuario["id"], request.form)
    except LookupError:
        abort(404)
    except PermissionError:
        abort(403)
    except (ValueError, db.ErrorIntegridad) as error:
        flash(str(error) if isinstance(error, ValueError) else "Ya valoraste esta operación.")
    else:
        flash("Tu valoración fue registrada. Gracias por compartir tu experiencia.")
    if tipo == "prestamo":
        return redirect(url_for("objetos.detalle_prestamo", prestamo_id=operacion_id))
    return redirect(url_for("objetos.detalle_acuerdo", tipo=tipo, acuerdo_id=operacion_id))
