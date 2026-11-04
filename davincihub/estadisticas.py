"""C6 / RF-31: estadísticas agregadas, sin contenido de conversaciones privadas."""

from datetime import date, timedelta

from flask import Blueprint, g, render_template, request

from davincihub import db, seguridad
from davincihub.objetos.datos import CATEGORIAS
from davincihub.utiles import hoy_local

bp = Blueprint("estadisticas", __name__, url_prefix="/admin/estadisticas")
PERIODOS = (4, 8, 12)

# Fuente, fecha y condición compartidas entre totales y evolución.
# Solo identificadores internos constantes; ningún fragmento viene de la petición.
_P = "FROM publicaciones p WHERE p.oculto = 0"
_R = "FROM respuestas r JOIN preguntas p ON p.id = r.pregunta_id WHERE r.oculto = 0 AND p.oculto = 0"
_A = "FROM actividades a WHERE a.oculto = 0"
_RES = ("FROM reservas r"
        " WHERE NOT EXISTS (SELECT 1 FROM actividades oc WHERE oc.reserva_id = r.id AND oc.oculto = 1)")
_OP = "JOIN publicaciones p ON p.id = a.publicacion_id"
_VISIBLE_OP = "p.oculto = 0"
_VISIBLE_INTER = ("p.oculto = 0 AND NOT EXISTS (SELECT 1 FROM publicaciones ofr"
                  " WHERE ofr.id = a.publicacion_ofrecida_id AND ofr.oculto = 1)")
_OPERACIONES = (
    "SELECT 'prestamo' AS tipo, a.id, a.creado, a.estado, p.oculto AS oculta"
    " FROM prestamos a " + _OP + " UNION ALL"
    " SELECT 'venta', a.id, a.creado, a.estado, p.oculto FROM ventas a " + _OP + " UNION ALL"
    " SELECT 'intercambio', a.id, a.creado, a.estado, CASE WHEN " + _VISIBLE_INTER
    + " THEN 0 ELSE 1 END FROM intercambios a " + _OP
)

# (clave, etiqueta, explicación, grupo, ((fecha, FROM/WHERE), ...))
METRICAS = (
    ("usuarios", "Usuarios registrados", "Todas las cuentas, incluidos administradores y cuentas bloqueadas.",
     "registros", (("u.creado", "FROM usuarios u WHERE 1 = 1"),)),
    ("publicaciones", "Publicaciones", "Activas, pausadas y cerradas; sin las ocultas por moderación.",
     "contenidos", (("p.creado", _P),)),
    ("preguntas", "Preguntas", "Preguntas no ocultas del foro.",
     "contenidos", (("p.creado", "FROM preguntas p WHERE p.oculto = 0"),)),
    ("respuestas", "Respuestas", "Respuestas no ocultas en preguntas no ocultas.",
     "contenidos", (("r.creado", _R),)),
    ("reservas", "Reservas", "Confirmadas y canceladas; sin reservas de actividades ocultas.",
     "contenidos", (("r.creado", _RES),)),
    ("actividades", "Actividades", "Todos los estados; sin actividades ocultas por moderación.",
     "contenidos", (("a.creado", _A),)),
    ("mensajes", "Mensajes enviados", "Solo la cantidad. No se muestran textos ni participantes.",
     "interacciones", (("m.creado", "FROM mensajes m WHERE 1 = 1"),)),
    ("conexiones", "Conexiones aceptadas", "Vínculos actualmente aceptados; fecha del pedido original.",
     "interacciones", (("c.creado", "FROM conexiones c WHERE c.estado = 'aceptada'"),)),
    ("propuestas", "Pedidos y propuestas", "Pedidos de préstamo y propuestas de venta o intercambio, incluidos cancelados.",
     "interacciones", (("op.creado", "FROM (" + _OPERACIONES + ") op WHERE op.oculta = 0"),)),
    ("prestamos", "Préstamos devueltos", "Préstamos finalizados con devolución registrada.",
     "interacciones", (("COALESCE(a.devuelto, a.creado)", "FROM prestamos a " + _OP
                        + " WHERE " + _VISIBLE_OP + " AND a.estado = 'devuelto'"),)),
    ("ventas", "Ventas completadas", "Ventas confirmadas por ambas partes, sin procesar pagos.",
     "interacciones", (("COALESCE(a.completado, a.creado)", "FROM ventas a " + _OP
                        + " WHERE " + _VISIBLE_OP + " AND a.estado = 'completada'"),)),
    ("intercambios", "Intercambios completados", "Intercambios confirmados por ambas partes.",
     "interacciones", (("COALESCE(a.completado, a.creado)", "FROM intercambios a " + _OP
                        + " WHERE " + _VISIBLE_INTER + " AND a.estado = 'completado'"),)),
    ("opiniones", "Opiniones de operaciones", "Valoraciones sobre operaciones cuyos objetos no están ocultos.",
     "interacciones", (("v.creado", "FROM valoraciones_operaciones v JOIN (" + _OPERACIONES
                        + ") op ON op.tipo = v.tipo_operacion AND op.id = v.operacion_id WHERE op.oculta = 0"),)),
    ("utiles", "Respuestas útiles", "Votos de utilidad en respuestas y preguntas no ocultas.",
     "interacciones", (("v.creado", ("FROM valoraciones_respuestas v JOIN respuestas r ON r.id = v.respuesta_id"
                        " JOIN preguntas p ON p.id = r.pregunta_id WHERE r.oculto = 0 AND p.oculto = 0")),)),
    ("inscripciones", "Inscripciones", "Inscripciones existentes en actividades no ocultas.",
     "interacciones", (("i.creado", ("FROM inscripciones i JOIN actividades a ON a.id = i.actividad_id"
                        " WHERE a.oculto = 0")),)),
    ("busquedas", "Búsquedas guardadas", "Búsquedas de materiales, activas y cerradas.",
     "interacciones", (("s.creado", "FROM solicitudes s WHERE 1 = 1"),)),
)


def _dia_local(expresion):
    """Fechas ISO con zona a Buenos Aires; las fechas sin zona ya son locales."""
    con_zona = (f"(substr({expresion}, 11) LIKE '%+%' OR substr({expresion}, 11) LIKE '%-%'"
                f" OR substr({expresion}, length({expresion}), 1) = 'Z')")
    if g.db_es_pg:
        return (f"CAST(CASE WHEN {con_zona} THEN CAST({expresion} AS TIMESTAMPTZ)"
                " AT TIME ZONE 'America/Argentina/Buenos_Aires'"
                f" ELSE CAST({expresion} AS TIMESTAMP) END AS DATE)")
    return f"date({expresion}, CASE WHEN {con_zona} THEN '-3 hours' ELSE '+0 hours' END)"


def resumen(semanas=8, hoy=None):
    semanas = semanas if semanas in PERIODOS else 8
    hoy = hoy or date.fromisoformat(hoy_local())
    lunes = hoy - timedelta(days=hoy.weekday())
    inicio = lunes - timedelta(weeks=semanas - 1)
    db.get_db()
    conteos, diarios = [], []
    for clave, _, _, _, fuentes in METRICAS:
        for fecha, fuente in fuentes:
            conteos.append(f"SELECT '{clave}' AS clave, count(*) AS cantidad {fuente}")
            dia = _dia_local(fecha)
            diarios.append(f"SELECT '{clave}' AS clave, {dia} AS dia, count(*) AS cantidad {fuente}"
                           f" AND {dia} >= CAST(:desde AS DATE) AND {dia} <= CAST(:hasta AS DATE) GROUP BY {dia}"
                           if g.db_es_pg else
                           f"SELECT '{clave}' AS clave, {dia} AS dia, count(*) AS cantidad {fuente}"
                           f" AND {dia} >= :desde AND {dia} <= :hasta GROUP BY {dia}")
    totales = {fila["clave"]: fila["cantidad"] for fila in db.query(" UNION ALL ".join(conteos))}
    evolucion = [{"inicio": inicio + timedelta(weeks=n), "registros": 0, "contenidos": 0,
                  "interacciones": 0} for n in range(semanas)]
    grupos = {clave: grupo for clave, _, _, grupo, _ in METRICAS}
    for fila in db.query(" UNION ALL ".join(diarios), desde=inicio.isoformat(), hasta=hoy.isoformat()):
        dia = date.fromisoformat(str(fila["dia"]))
        indice = (dia - inicio).days // 7
        evolucion[indice][grupos[fila["clave"]]] += fila["cantidad"]
    maximo = max(1, *(fila[grupo] for fila in evolucion for grupo in ("registros", "contenidos", "interacciones")))
    for fila in evolucion:
        fila["fin"] = min(fila["inicio"] + timedelta(days=6), hoy)
    materias = db.query(
        "SELECT m.id, m.nombre, c.nombre AS carrera, count(*) AS cantidad FROM preguntas p"
        " JOIN materias m ON m.id = p.materia_id JOIN carreras c ON c.id = m.carrera_id"
        " WHERE p.oculto = 0 GROUP BY m.id, m.nombre, c.nombre ORDER BY cantidad DESC, m.nombre, c.nombre, m.id LIMIT 5"
    )
    categorias = db.query(
        "SELECT p.categoria, count(*) AS cantidad " + _P
        + " GROUP BY p.categoria ORDER BY cantidad DESC, p.categoria LIMIT 5"
    )
    for fila in categorias:
        fila["nombre"] = CATEGORIAS.get(fila["categoria"], "Otros materiales de estudio")
    return {"totales": totales, "evolucion": evolucion, "maximo": maximo,
            "materias": materias, "categorias": categorias, "semanas": semanas, "hoy": hoy,
            "metricas": [{"clave": clave, "nombre": nombre, "detalle": detalle, "grupo": grupo}
                         for clave, nombre, detalle, grupo, _ in METRICAS]}


@bp.get("/")
@seguridad.requiere_admin
def panel():
    valor = request.args.get("semanas", "8")
    semanas = int(valor) if valor in ("4", "8", "12") else 8
    respuesta = render_template("estadisticas.html", **resumen(semanas))
    return respuesta, {"Cache-Control": "private, no-store"}
