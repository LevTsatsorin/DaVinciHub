"""Intercambios y ventas entre estudiantes (C4 / RF-17)."""

from decimal import Decimal, InvalidOperation

from davincihub import db
from davincihub.notificaciones import notificar
from davincihub.objetos import datos, prestamos
from davincihub.utiles import ahora

TIPOS = {"intercambio": "Intercambio", "venta": "Venta"}
ESTADOS = {"propuesto": "Propuesto", "aceptado": "Aceptado", "completado": "Completado", "cancelado": "Cancelado"}
_CONFIG = {
    "intercambio": ("intercambios", "solicitante_id", dict(zip(ESTADOS, ESTADOS, strict=True))),
    "venta": ("ventas", "comprador_id", dict(zip(ESTADOS, ("propuesta", "aceptada", "completada", "cancelada"), strict=True))),
}


class ErrorAcuerdo(datos.ErrorPublicacion):
    pass


def _error(texto, campo="general"):
    raise ErrorAcuerdo({campo: texto})


def _config(tipo):
    if tipo not in _CONFIG:
        raise LookupError("No existe este tipo de acuerdo.")
    return _CONFIG[tipo]


def obtener(tipo, acuerdo_id):
    tabla, solicitante, estados = _config(tipo)
    extras = "a.oferta, a.publicacion_ofrecida_id, ofr.titulo AS titulo_ofrecido" if tipo == "intercambio" else "a.mensaje AS oferta, a.precio_acordado"
    union = " LEFT JOIN publicaciones ofr ON ofr.id = a.publicacion_ofrecida_id" if tipo == "intercambio" else ""
    fila = db.query_one(
        f"SELECT a.*, a.{solicitante} AS solicitante_id, p.autor_id AS propietario_id,"
        " p.titulo, p.categoria, p.estado AS estado_publicacion, p.oculto,"
        " du.nombre AS propietario_nombre, du.apellido AS propietario_apellido,"
        " du.bloqueado AS propietario_bloqueado, so.nombre AS solicitante_nombre,"
        f" so.apellido AS solicitante_apellido, so.bloqueado AS solicitante_bloqueado, {extras}"
        f" FROM {tabla} a JOIN publicaciones p ON p.id = a.publicacion_id"
        f" JOIN usuarios du ON du.id = p.autor_id JOIN usuarios so ON so.id = a.{solicitante}"
        + union + " WHERE a.id = :id", id=acuerdo_id,
    )
    if fila:
        fila["tipo"] = tipo
        fila["estado"] = next(k for k, v in estados.items() if v == fila["estado"])
        fila.setdefault("publicacion_ofrecida_id", None)
    return fila


def _relacionadas(publicacion_id):
    return db.query(
        "SELECT 'venta' AS tipo, id FROM ventas WHERE publicacion_id = :p"
        " UNION ALL SELECT 'intercambio' AS tipo, id FROM intercambios"
        " WHERE publicacion_id = :p OR publicacion_ofrecida_id = :p", p=publicacion_id,
    )


def reservada(publicacion_id, excepto=None):
    for referencia in _relacionadas(publicacion_id):
        if (referencia["tipo"], referencia["id"]) == excepto:
            continue
        if obtener(referencia["tipo"], referencia["id"])["estado"] in ("aceptado", "completado"):
            return True
    return False


def abierta_propia(publicacion_id, usuario_id):
    for referencia in _relacionadas(publicacion_id):
        a = obtener(referencia["tipo"], referencia["id"])
        if a["publicacion_id"] == publicacion_id and a["solicitante_id"] == usuario_id and a["estado"] in ("propuesto", "aceptado"):
            return a
    return None


def _publicaciones(a):
    return sorted({p for p in (a["publicacion_id"], a.get("publicacion_ofrecida_id")) if p is not None})


def _bloquear(a):
    for publicacion_id in _publicaciones(a):
        if not db.bloquear_fila("publicaciones", publicacion_id):
            if publicacion_id == a["publicacion_id"]:
                raise LookupError("No existe la publicación.")
            _error("El objeto ofrecido ya no existe.", "publicacion_ofrecida_id")


def _disponible(publicacion_id, modalidad, autor=None, excepto=None):
    p = datos.obtener(publicacion_id)
    if p is None:
        raise LookupError("No existe la publicación.")
    if (p["estado"] != "activa" or p["oculto"] or p["autor_bloqueado"]
            or p["modalidad"] != modalidad or (autor is not None and p["autor_id"] != autor)):
        _error("El objeto debe estar activo, disponible y pertenecer al estudiante que lo ofrece.")
    if prestamos.ocupado(publicacion_id) or reservada(publicacion_id, excepto):
        _error("Uno de los objetos ya tiene otra operación en curso o completada.")
    return p


def ofrecibles(usuario_id):
    filas = db.query(
        "SELECT id, titulo FROM publicaciones WHERE autor_id = :autor AND modalidad = 'intercambio'"
        " AND estado = 'activa' AND oculto = 0 ORDER BY titulo", autor=usuario_id,
    )
    return [p for p in filas if not prestamos.ocupado(p["id"]) and not reservada(p["id"])]


def _precio(form):
    try:
        valor = Decimal((form.get("precio_acordado") or "").strip())
        if not valor.is_finite() or not 0 < valor <= datos.PRECIO_MAXIMO or valor != valor.quantize(Decimal("0.01")):
            raise ValueError
        return float(valor)
    except (InvalidOperation, ValueError):
        _error("Ingresá un precio mayor a 0, con hasta 2 decimales (máximo $999.999.999,99).", "precio_acordado")


def _oferta(form, tipo):
    oferta = (form.get("oferta") or "").strip()
    if tipo == "intercambio" and not oferta:
        _error("Describí qué ofrecés a cambio.", "oferta")
    if len(oferta) > 2000:
        _error("Usá como máximo 2000 caracteres.", "oferta")
    return oferta


def _ofrecida_id(form, tipo):
    if tipo != "intercambio":
        return None
    texto = (form.get("publicacion_ofrecida_id") or "").strip()
    if not texto:
        return None
    try:
        if len(texto) > 10 or not 0 < int(texto) <= 2147483647 or not texto.isdecimal():
            raise ValueError
        return int(texto)
    except ValueError:
        _error("Elegí uno de tus objetos disponibles o dejá el campo vacío.", "publicacion_ofrecida_id")


def _aviso(usuario_id, a, texto):
    notificar(usuario_id, "objetos", texto, f'/objetos/acuerdos/{a["tipo"]}/{a["id"]}')


def _movimiento(a, anterior, nuevo, actor, detalle):
    db.execute(
        "INSERT INTO acuerdos_movimientos (tipo_operacion, operacion_id, estado_anterior, estado_nuevo, actor_id, detalle, creado)"
        " VALUES (:tipo, :id, :anterior, :nuevo, :actor, :detalle, :creado)", tipo=a["tipo"], id=a["id"],
        anterior=anterior, nuevo=nuevo, actor=actor, detalle=detalle, creado=ahora(),
    )


def proponer(publicacion_id, usuario_id, form):
    datos._estudiante(usuario_id)
    p = datos.obtener(publicacion_id)
    if p is None:
        raise LookupError("No existe la publicación.")
    tipo = p["modalidad"]
    tabla, solicitante, _ = _config(tipo)
    oferta = _oferta(form, tipo)
    ofrecida = _ofrecida_id(form, tipo)
    precio = _precio(form) if tipo == "venta" else None
    with db.transaccion():
        _bloquear({"publicacion_id": publicacion_id, "publicacion_ofrecida_id": ofrecida})
        p = _disponible(publicacion_id, tipo)
        if p["autor_id"] == usuario_id:
            _error("No podés operar sobre tu propia publicación.")
        if abierta_propia(publicacion_id, usuario_id):
            _error("Ya tenés una propuesta abierta para esta publicación.")
        if ofrecida:
            _disponible(ofrecida, "intercambio", autor=usuario_id)
        if tipo == "intercambio":
            fila = db.query_one(
                "INSERT INTO intercambios (publicacion_id, solicitante_id, oferta, publicacion_ofrecida_id, creado)"
                " VALUES (:publicacion, :usuario, :oferta, :ofrecida, :creado) RETURNING id",
                publicacion=publicacion_id, usuario=usuario_id, oferta=oferta, ofrecida=ofrecida, creado=ahora(),
            )
        else:
            fila = db.query_one(
                f"INSERT INTO {tabla} (publicacion_id, {solicitante}, precio_acordado, mensaje, creado)"
                " VALUES (:publicacion, :usuario, :precio, :mensaje, :creado) RETURNING id",
                publicacion=publicacion_id, usuario=usuario_id, precio=precio, mensaje=oferta, creado=ahora(),
            )
        a = obtener(tipo, fila["id"])
        _movimiento(a, None, "propuesto", usuario_id, "Propuesta enviada.")
        _aviso(p["autor_id"], a, f'Nueva propuesta de {tipo} para «{p["titulo"]}».')
    return tipo, fila["id"]


def acciones(a, usuario_id):
    propietario = a["propietario_id"] == usuario_id
    if a["estado"] == "propuesto":
        return ["aceptar", "rechazar"] if propietario else ["cancelar"]
    if a["estado"] == "aceptado":
        confirmado = a["confirmado_propietario"] if propietario else a["confirmado_solicitante"]
        return (["confirmar"] if not confirmado else []) + ["cancelar"]
    return []


def _cancelar(a, usuario_id, motivo):
    tabla, _, estados = _config(a["tipo"])
    db.execute(f"UPDATE {tabla} SET estado = :estado, motivo_cierre = :motivo WHERE id = :id",
               estado=estados["cancelado"], motivo=motivo, id=a["id"])
    _movimiento(a, a["estado"], "cancelado", usuario_id, motivo)


def _rechazar_otras(a, usuario_id):
    vistas = {(a["tipo"], a["id"])}
    for publicacion in _publicaciones(a):
        for ref in _relacionadas(publicacion):
            clave = (ref["tipo"], ref["id"])
            if clave in vistas:
                continue
            vistas.add(clave)
            otra = obtener(*clave)
            if otra["estado"] != "propuesto":
                continue
            tabla, _, _ = _config(otra["tipo"])
            db.bloquear_fila(tabla, otra["id"])
            _cancelar(otra, usuario_id, "Rechazada automáticamente: se aceptó otra propuesta para uno de los objetos.")
            for usuario in (otra["propietario_id"], otra["solicitante_id"]):
                _aviso(usuario, otra, f'La propuesta para «{otra["titulo"]}» fue rechazada porque se aceptó otra operación.')


def cambiar(tipo, acuerdo_id, usuario_id, accion):
    datos._estudiante(usuario_id)
    previo = obtener(tipo, acuerdo_id)
    if previo is None:
        raise LookupError("No existe la propuesta.")
    if usuario_id not in (previo["propietario_id"], previo["solicitante_id"]):
        raise PermissionError("Esta propuesta no te pertenece.")
    tabla, _, estados = _config(tipo)
    with db.transaccion():
        _bloquear(previo)
        db.bloquear_fila(tabla, acuerdo_id)
        a = obtener(tipo, acuerdo_id)
        if accion not in acciones(a, usuario_id):
            _error("Esta acción no está permitida en el estado actual del acuerdo.")
        otro = a["solicitante_id"] if usuario_id == a["propietario_id"] else a["propietario_id"]
        if accion == "aceptar":
            if a["solicitante_bloqueado"]:
                _error("El solicitante está bloqueado. No se puede aceptar esta propuesta.")
            _disponible(a["publicacion_id"], tipo, excepto=(tipo, acuerdo_id))
            if a["publicacion_ofrecida_id"]:
                _disponible(a["publicacion_ofrecida_id"], "intercambio", autor=a["solicitante_id"], excepto=(tipo, acuerdo_id))
            db.execute(f"UPDATE {tabla} SET estado = :estado WHERE id = :id", estado=estados["aceptado"], id=acuerdo_id)
            _movimiento(a, "propuesto", "aceptado", usuario_id, "El propietario aceptó la propuesta.")
            _rechazar_otras(a, usuario_id)
            _aviso(otro, a, f'Tu propuesta para «{a["titulo"]}» fue aceptada. Coordiná la entrega.')
        elif accion == "confirmar":
            campo = "confirmado_propietario" if usuario_id == a["propietario_id"] else "confirmado_solicitante"
            db.execute(f"UPDATE {tabla} SET {campo} = 1 WHERE id = :id", id=acuerdo_id)
            actualizado = obtener(tipo, acuerdo_id)
            if actualizado["confirmado_propietario"] and actualizado["confirmado_solicitante"]:
                db.execute(f"UPDATE {tabla} SET estado = :estado, completado = :fecha WHERE id = :id",
                           estado=estados["completado"], fecha=ahora(), id=acuerdo_id)
                for p in _publicaciones(a):
                    db.execute("UPDATE publicaciones SET estado = 'cerrada' WHERE id = :id", id=p)
                _movimiento(a, "aceptado", "completado", usuario_id, "Ambas partes confirmaron la operación. Publicaciones cerradas.")
                for usuario in (a["propietario_id"], a["solicitante_id"]):
                    _aviso(usuario, a, f'La operación de {tipo} de «{a["titulo"]}» se completó.')
            else:
                _movimiento(a, "aceptado", "aceptado", usuario_id, "Confirmó que concretó la operación; falta la confirmación de la otra persona.")
                _aviso(otro, a, f'La otra persona confirmó la operación de «{a["titulo"]}». Falta tu confirmación.')
        else:
            motivo = "Propuesta rechazada por el propietario." if accion == "rechazar" else "Operación cancelada por un participante."
            _cancelar(a, usuario_id, motivo)
            _aviso(otro, a, f'La propuesta para «{a["titulo"]}» fue ' + ("rechazada." if accion == "rechazar" else "cancelada."))


def movimientos(tipo, acuerdo_id):
    return db.query(
        "SELECT m.*, u.nombre, u.apellido FROM acuerdos_movimientos m LEFT JOIN usuarios u ON u.id = m.actor_id"
        " WHERE tipo_operacion = :tipo AND operacion_id = :id ORDER BY m.id", tipo=tipo, id=acuerdo_id,
    )


def listar(usuario_id, vista="enviadas", tipo="", estado="", pagina=1):
    vista = vista if vista in ("enviadas", "recibidas") else "enviadas"
    tipo = tipo if tipo in TIPOS else ""
    estado = estado if estado in ESTADOS else ""
    partes, params = [], {"usuario": usuario_id}
    for tipo_actual in ([tipo] if tipo else TIPOS):
        tabla, solicitante, estados = _config(tipo_actual)
        condicion = f"a.{solicitante} = :usuario" if vista == "enviadas" else "p.autor_id = :usuario"
        if estado:
            condicion += f" AND a.estado = :estado_{tipo_actual}"
            params[f"estado_{tipo_actual}"] = estados[estado]
        partes.append(f"SELECT '{tipo_actual}' AS tipo, a.id, a.creado FROM {tabla} a"
                      " JOIN publicaciones p ON p.id = a.publicacion_id WHERE " + condicion)
    consulta = " UNION ALL ".join(partes)
    total = db.query_one("SELECT count(*) AS n FROM (" + consulta + ") AS acuerdos", **params)["n"]
    paginas = max(1, (total + datos.POR_PAGINA - 1) // datos.POR_PAGINA)
    pagina = min(max(1, pagina), paginas)
    filas = db.query("SELECT * FROM (" + consulta + ") AS acuerdos ORDER BY creado DESC, tipo, id DESC LIMIT :limite OFFSET :salto",
                     limite=datos.POR_PAGINA, salto=(pagina - 1) * datos.POR_PAGINA, **params)
    return {"acuerdos": [obtener(f["tipo"], f["id"]) for f in filas], "total": total,
            "pagina": pagina, "paginas": paginas, "vista": vista, "tipo": tipo, "estado": estado}
