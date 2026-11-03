"""RF-24: reputación calculada sobre operaciones finalizadas."""
from flask import Blueprint, abort, flash, g, redirect, request, url_for

from davincihub import db, seguridad
from davincihub.notificaciones import notificar
from davincihub.objetos import acuerdos, datos, prestamos
from davincihub.utiles import ahora

bp = Blueprint("reputacion", __name__, url_prefix="/reputacion")
TABLAS = {"prestamo": "prestamos", "intercambio": "intercambios", "venta": "ventas"}
# clave, nombre, mínimo de opiniones, promedio mínimo
INSIGNIAS = (("oro", "Oro", 10, 4.5), ("plata", "Plata", 6, 4.0), ("bronce", "Bronce", 3, 3.5))


def insignia(cantidad, promedio):
    for clave, nombre, minimo, piso in INSIGNIAS:
        if cantidad >= minimo and float(promedio) >= piso:
            return {"clave": clave, "nombre": nombre}
    return None


def _resumen(cantidad, promedio):
    return {
        "cantidad": cantidad,
        "promedio": f"{float(promedio):.1f}".replace(".", ",") if cantidad else None,
        "opiniones": "1 opinión" if cantidad == 1 else f"{cantidad} opiniones",
        "insignia": insignia(cantidad, promedio) if cantidad else None,
    }


@bp.app_template_global("reputacion_de")
def reputacion_de(usuario_id):
    if "reputaciones" not in g:
        g.reputaciones = {
            f["receptor_id"]: _resumen(f["cantidad"], f["promedio"])
            for f in db.query(
                "SELECT receptor_id, COUNT(*) AS cantidad, AVG(valor) AS promedio"
                " FROM valoraciones_operaciones GROUP BY receptor_id"
            )
        }
    return g.reputaciones.get(usuario_id) or _resumen(0, None)


def opiniones_de(usuario_id, limite, salto=0):
    return db.query(
        "SELECT v.*, u.nombre, u.apellido, u.bloqueado AS autor_bloqueado,"
        " EXISTS (SELECT 1 FROM fotos_perfil f WHERE f.usuario_id = u.id) AS tiene_foto,"
        " (p.oculto = 0 AND du.bloqueado = 0) AS publicacion_visible"
        " FROM valoraciones_operaciones v JOIN usuarios u ON u.id = v.autor_id"
        " JOIN (SELECT 'prestamo' AS tipo, id, publicacion_id FROM prestamos"
        " UNION ALL SELECT 'intercambio', id, publicacion_id FROM intercambios"
        " UNION ALL SELECT 'venta', id, publicacion_id FROM ventas) op"
        " ON op.tipo = v.tipo_operacion AND op.id = v.operacion_id"
        " JOIN publicaciones p ON p.id = op.publicacion_id JOIN usuarios du ON du.id = p.autor_id"
        " WHERE v.receptor_id = :id ORDER BY v.creado DESC, v.id DESC LIMIT :limite OFFSET :salto",
        id=usuario_id, limite=limite, salto=salto,
    )


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
        nombre = op["propietario_nombre"] if autor_id == op["propietario_id"] else op["solicitante_nombre"]
        ruta = f"/objetos/prestamos/{operacion_id}" if tipo == "prestamo" else f"/objetos/acuerdos/{tipo}/{operacion_id}"
        notificar(receptor, "objetos", f"{nombre} te dejó una valoración de {valor}/5 por «{op['titulo']}».", ruta)


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
