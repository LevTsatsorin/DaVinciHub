"""Historial de publicaciones y operaciones de cada estudiante (C5 / RF-18)."""

from davincihub import db
from davincihub.objetos import acuerdos, datos, prestamos

TIPOS = {"publicacion": "Publicaciones", "prestamo": "Préstamos", "intercambio": "Intercambios", "venta": "Ventas"}
NOMBRES = {"publicacion": "Publicación", "prestamo": "Préstamo", "intercambio": "Intercambio", "venta": "Venta"}
ESTADOS_POR_TIPO = {
    "publicacion": datos.ESTADOS, "prestamo": prestamos.ESTADOS,
    "intercambio": acuerdos.ESTADOS, "venta": acuerdos.ESTADOS,
}
ESTADOS = {clave: nombre for estados in ESTADOS_POR_TIPO.values() for clave, nombre in estados.items()}
FINALIZADOS = ("devuelto", "completado")

_PUBLICACIONES = (
    "SELECT 'publicacion' AS tipo, p.id, p.id AS publicacion_id, p.titulo, p.categoria, p.modalidad, p.oculto,"
    " p.estado, p.creado, CAST(NULL AS TEXT) AS cierre, CAST(NULL AS TEXT) AS fecha_entrega,"
    " CAST(NULL AS TEXT) AS fecha_devolucion, p.precio AS importe, 1 AS es_propietario,"
    " CAST(NULL AS INTEGER) AS otro_id, CAST(NULL AS TEXT) AS otro_nombre, CAST(NULL AS TEXT) AS otro_apellido,"
    " 0 AS otro_tiene_foto, CAST(NULL AS INTEGER) AS valor"
    " FROM publicaciones p WHERE p.autor_id = :usuario"
)
_PRESTAMOS = (
    "SELECT 'prestamo' AS tipo, a.id, a.publicacion_id, p.titulo, p.categoria, p.modalidad, p.oculto,"
    " a.estado, a.creado, COALESCE(a.devuelto, (SELECT MAX(m.creado) FROM prestamos_movimientos m"
    " WHERE m.prestamo_id = a.id AND m.estado_nuevo = 'cancelado')) AS cierre,"
    " a.fecha_entrega, a.fecha_devolucion, CAST(NULL AS DOUBLE PRECISION) AS importe,"
    " CASE WHEN p.autor_id = :usuario THEN 1 ELSE 0 END AS es_propietario,"
    " o.id AS otro_id, o.nombre AS otro_nombre, o.apellido AS otro_apellido,"
    " CASE WHEN EXISTS (SELECT 1 FROM fotos_perfil f WHERE f.usuario_id = o.id) THEN 1 ELSE 0 END AS otro_tiene_foto, v.valor"
    " FROM prestamos a JOIN publicaciones p ON p.id = a.publicacion_id"
    " JOIN usuarios o ON o.id = CASE WHEN p.autor_id = :usuario THEN a.solicitante_id ELSE p.autor_id END"
    " LEFT JOIN valoraciones_operaciones v ON v.tipo_operacion = 'prestamo'"
    " AND v.operacion_id = a.id AND v.autor_id = :usuario"
    " WHERE p.autor_id = :usuario OR a.solicitante_id = :usuario"
)


def _acuerdos_sql(tipo):
    tabla, solicitante, estados = acuerdos._config(tipo)
    casos = " ".join(f"WHEN '{real}' THEN '{comun}'" for comun, real in estados.items())
    importe = "a.precio_acordado" if tipo == "venta" else "CAST(NULL AS DOUBLE PRECISION)"
    return (
        f"SELECT '{tipo}' AS tipo, a.id, a.publicacion_id, p.titulo, p.categoria, p.modalidad, p.oculto,"
        f" CASE a.estado {casos} END AS estado, a.creado, COALESCE(a.completado, (SELECT MAX(m.creado)"
        f" FROM acuerdos_movimientos m WHERE m.tipo_operacion = '{tipo}' AND m.operacion_id = a.id"
        " AND m.estado_nuevo = 'cancelado')) AS cierre, CAST(NULL AS TEXT) AS fecha_entrega,"
        f" CAST(NULL AS TEXT) AS fecha_devolucion, {importe} AS importe,"
        " CASE WHEN p.autor_id = :usuario THEN 1 ELSE 0 END AS es_propietario,"
        " o.id AS otro_id, o.nombre AS otro_nombre, o.apellido AS otro_apellido,"
    " CASE WHEN EXISTS (SELECT 1 FROM fotos_perfil f WHERE f.usuario_id = o.id) THEN 1 ELSE 0 END AS otro_tiene_foto, v.valor"
        f" FROM {tabla} a JOIN publicaciones p ON p.id = a.publicacion_id"
        f" JOIN usuarios o ON o.id = CASE WHEN p.autor_id = :usuario THEN a.{solicitante} ELSE p.autor_id END"
        f" LEFT JOIN valoraciones_operaciones v ON v.tipo_operacion = '{tipo}'"
        " AND v.operacion_id = a.id AND v.autor_id = :usuario"
        f" WHERE p.autor_id = :usuario OR a.{solicitante} = :usuario"
    )


def _union(tipos):
    consultas = {"publicacion": _PUBLICACIONES, "prestamo": _PRESTAMOS,
                 "intercambio": _acuerdos_sql("intercambio"), "venta": _acuerdos_sql("venta")}
    return " UNION ALL ".join(consultas[t] for t in tipos)


def cantidades(usuario_id):
    filas = db.query(f"SELECT h.tipo, count(*) AS n FROM ({_union(TIPOS)}) AS h GROUP BY h.tipo", usuario=usuario_id)
    return {f["tipo"]: f["n"] for f in filas}


def listar(usuario_id, tipo="", estado="", pagina=1):
    tipo = tipo if tipo in TIPOS else ""
    disponibles = ESTADOS_POR_TIPO[tipo] if tipo else ESTADOS
    estado = estado if estado in disponibles else ""
    union = _union([tipo] if tipo else TIPOS)
    filtro = " WHERE h.estado = :estado" if estado else ""
    params = {"usuario": usuario_id, **({"estado": estado} if estado else {})}
    desde = f" FROM ({union}) AS h{filtro}"
    total = db.query_one("SELECT count(*) AS n" + desde, **params)["n"]
    paginas = max(1, (total + datos.POR_PAGINA - 1) // datos.POR_PAGINA)
    pagina = min(max(1, pagina), paginas)
    operaciones = db.query(
        "SELECT h.*" + desde + " ORDER BY h.creado DESC, h.tipo, h.id DESC LIMIT :limite OFFSET :salto",
        limite=datos.POR_PAGINA, salto=(pagina - 1) * datos.POR_PAGINA, **params,
    )
    return {"operaciones": operaciones, "total": total, "pagina": pagina, "paginas": paginas,
            "tipo": tipo, "estado": estado, "estados_disponibles": disponibles}
