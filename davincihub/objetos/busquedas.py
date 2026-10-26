"""Solicitudes de materiales y coincidencias automáticas (RF-14 y RF-15)."""

import re
from decimal import Decimal, InvalidOperation

from davincihub import db
from davincihub.notificaciones import notificar
from davincihub.objetos import datos
from davincihub.utiles import ahora, sin_acentos

CATEGORIAS = {"todas": "Todas las categorías", **datos.CATEGORIAS}

MODALIDADES = {
    "cualquiera": "Cualquier modalidad",
    "venta": "Comprar",
    "intercambio": "Intercambiar",
    "prestamo": "Pedir prestado",
}
_IGNORADAS = frozenset(
    ["a", "al", "algo", "ante", "bajo", "busco", "buscar", "buena", "buenas", "bueno", "buenos",
     "como", "con", "contra", "cual", "cualquier", "de", "del", "desde", "donde", "el", "ella",
     "en", "entre", "es", "esa", "ese", "eso", "esta", "estas", "este", "estos", "estoy", "hay",
     "la", "las", "lo", "los", "mas", "me", "mi", "mis", "muy", "necesito", "no", "o", "otra",
     "otro", "para", "pero", "por", "que", "quiero", "se", "sin", "sobre", "su", "sus", "te",
     "tengo", "tu", "tus", "un", "una", "unas", "uno", "unos", "usado", "usada", "nuevo", "nueva",
     "y", "ya", "anda", "bien", "completa", "completo", "correctamente", "correcto", "estado",
     "excelente", "funciona", "funcionando", "funcione", "impecable", "incluye", "original",
     "perfecta", "perfecto", "poco", "sirve", "toda", "todo", "uso"]
)


class ErrorBusqueda(datos.ErrorPublicacion):
    pass


def _singular(palabra: str) -> str:
    if len(palabra) > 4 and palabra.endswith("ces"):
        return palabra[:-3] + "z"
    if len(palabra) > 3 and palabra.endswith("s"):
        return palabra[:-1]
    return palabra


def palabras(texto: str) -> set[str]:
    return {
        _singular(p) for p in re.findall(r"[^\W_]+", sin_acentos(texto or ""))
        if (len(p) >= 3 or p in {"pc", "vr", "a3", "a4", "2d", "3d"})
        and not p.isdigit() and p not in _IGNORADAS and _singular(p) not in _IGNORADAS
    }


def _parecidas(una: str, otra: str) -> bool:
    corta, larga = sorted((una, otra), key=len)
    return corta == larga or (len(corta) >= 5 and larga.startswith(corta))


def coincide(solicitud: dict, publicacion: dict) -> bool:
    """Categoría elegida, modalidad, presupuesto y palabras completas o prefijos."""
    if (solicitud["autor_id"] == publicacion["autor_id"]
            or (solicitud["categoria"] != "todas"
                and solicitud["categoria"] != publicacion["categoria"])):
        return False
    modalidad = solicitud.get("modalidad", "cualquiera")
    if modalidad != "cualquiera" and modalidad != publicacion["modalidad"]:
        return False
    presupuesto = solicitud.get("presupuesto_max")
    if publicacion["modalidad"] == "venta" and presupuesto is not None:
        precio = publicacion.get("precio")
        if precio is None or Decimal(str(precio)) > Decimal(str(presupuesto)):
            return False
    buscadas = palabras(solicitud["titulo"] + " " + (solicitud.get("descripcion") or ""))
    ofrecidas = palabras(publicacion["titulo"] + " " + (publicacion.get("descripcion") or ""))
    return any(_parecidas(buscada, ofrecida) for buscada in buscadas for ofrecida in ofrecidas)


def _validar(form) -> dict:
    errores = {}
    campos = {}
    for campo, limite in (("titulo", 120), ("descripcion", 2000)):
        valor = (form.get(campo) or "").strip()
        if campo == "titulo" and not valor:
            errores[campo] = "Contá qué objeto estás buscando."
        elif len(valor) > limite:
            errores[campo] = f"Usá como máximo {limite} caracteres."
        campos[campo] = valor
    if campos["titulo"] and not palabras(campos["titulo"] + " " + campos["descripcion"]):
        errores["titulo"] = "Incluí el nombre del objeto, por ejemplo: calculadora científica."
    campos["categoria"] = form.get("categoria") or ""
    if campos["categoria"] not in CATEGORIAS:
        errores["categoria"] = "Elegí una categoría válida."
    campos["modalidad"] = form.get("modalidad") or "cualquiera"
    if campos["modalidad"] not in MODALIDADES:
        errores["modalidad"] = "Elegí una modalidad válida."
    campos["presupuesto_max"] = None
    texto = (form.get("presupuesto_max") or "").strip()
    if campos["modalidad"] == "venta" and texto:
        try:
            valor = Decimal(texto)
            if not valor.is_finite() or not 0 < valor <= datos.PRECIO_MAXIMO:
                raise ValueError
            if valor != valor.quantize(Decimal("0.01")):
                raise ValueError
            campos["presupuesto_max"] = float(valor)
        except (InvalidOperation, ValueError):
            errores["presupuesto_max"] = "Ingresá un presupuesto mayor a 0, con hasta 2 decimales (máximo $999.999.999,99)."
    if errores:
        raise ErrorBusqueda(errores)
    return campos


def obtener(solicitud_id: int) -> dict | None:
    return db.query_one("SELECT * FROM solicitudes WHERE id = :id", id=solicitud_id)


def crear(usuario_id: int, form) -> tuple[int, int]:
    datos._estudiante(usuario_id)
    campos = _validar(form)
    with db.transaccion():
        solicitud = db.query_one(
            "INSERT INTO solicitudes (autor_id, titulo, descripcion, categoria, modalidad,"
            " presupuesto_max, creado) VALUES (:autor, :titulo, :descripcion, :categoria,"
            " :modalidad, :presupuesto_max, :creado) RETURNING id",
            autor=usuario_id, creado=ahora(), **campos,
        )
        cantidad = detectar_para_busqueda(solicitud["id"])
    return solicitud["id"], cantidad


def _registrar(solicitud: dict, publicacion: dict) -> bool:
    if not coincide(solicitud, publicacion):
        return False
    fila = db.query_one(
        "INSERT INTO coincidencias (solicitud_id, publicacion_id, creado)"
        " VALUES (:solicitud, :publicacion, :creado)"
        " ON CONFLICT (solicitud_id, publicacion_id) DO NOTHING RETURNING id",
        solicitud=solicitud["id"], publicacion=publicacion["id"], creado=ahora(),
    )
    if fila is None:
        return False
    notificar(
        solicitud["autor_id"], "objetos",
        f'Encontramos una posible coincidencia para tu búsqueda «{solicitud["titulo"]}»: '
        f'{publicacion["titulo"]}.',
        f'/objetos/busquedas/{solicitud["id"]}',
    )
    return True


def detectar_para_busqueda(solicitud_id: int) -> int:
    with db.transaccion():
        if not db.bloquear_fila("solicitudes", solicitud_id):
            return 0
        solicitud = db.query_one(
            "SELECT s.* FROM solicitudes s JOIN usuarios u ON u.id = s.autor_id"
            " WHERE s.id = :id AND s.estado = 'activa' AND u.bloqueado = 0",
            id=solicitud_id,
        )
        if solicitud is None:
            return 0
        publicaciones = db.query(
            "SELECT p.* FROM publicaciones p JOIN usuarios u ON u.id = p.autor_id"
            " WHERE p.estado = 'activa' AND (:categoria = 'todas' OR p.categoria = :categoria)"
            " AND p.autor_id <> :autor AND u.bloqueado = 0 ORDER BY p.id",
            categoria=solicitud["categoria"], autor=solicitud["autor_id"],
        )
        return sum(_registrar(solicitud, p) for p in publicaciones)


def detectar_para_publicacion(publicacion_id: int) -> int:
    with db.transaccion():
        publicacion = db.query_one(
            "SELECT p.* FROM publicaciones p JOIN usuarios u ON u.id = p.autor_id"
            " WHERE p.id = :id AND p.estado = 'activa' AND u.bloqueado = 0",
            id=publicacion_id,
        )
        if publicacion is None:
            return 0
        solicitudes = db.query(
            "SELECT s.id FROM solicitudes s JOIN usuarios u ON u.id = s.autor_id"
            " WHERE s.estado = 'activa' AND (s.categoria = 'todas' OR s.categoria = :categoria)"
            " AND s.autor_id <> :autor AND u.bloqueado = 0 ORDER BY s.id",
            categoria=publicacion["categoria"], autor=publicacion["autor_id"],
        )
        cantidad = 0
        for s in solicitudes:
            # La misma fila se bloquea al cerrar una búsqueda: no se avisa después del cierre.
            if not db.bloquear_fila("solicitudes", s["id"]):
                continue
            solicitud = obtener(s["id"])
            if solicitud["estado"] == "activa":
                cantidad += _registrar(solicitud, publicacion)
        return cantidad


def coincidencias_de(solicitud: dict) -> list[dict]:
    publicaciones = db.query(
        "SELECT p.*, u.nombre AS autor_nombre, u.apellido AS autor_apellido, c.nombre AS carrera"
        " FROM coincidencias co JOIN publicaciones p ON p.id = co.publicacion_id"
        " JOIN usuarios u ON u.id = p.autor_id LEFT JOIN carreras c ON c.id = p.carrera_id"
        " WHERE co.solicitud_id = :id AND p.estado = 'activa' AND u.bloqueado = 0"
        " ORDER BY co.creado DESC, co.id DESC",
        id=solicitud["id"],
    )
    return [p for p in publicaciones if coincide(solicitud, p)]


def listar_de(usuario_id: int, estado: str = "activa", pagina: int = 1) -> dict:
    estado = estado if estado in ("activa", "cerrada") else "activa"
    total = db.query_one(
        "SELECT count(*) AS n FROM solicitudes WHERE autor_id = :autor AND estado = :estado",
        autor=usuario_id, estado=estado,
    )["n"]
    paginas = max(1, (total + datos.POR_PAGINA - 1) // datos.POR_PAGINA)
    pagina = min(max(1, pagina), paginas)
    solicitudes = db.query(
        "SELECT * FROM solicitudes WHERE autor_id = :autor AND estado = :estado"
        " ORDER BY creado DESC, id DESC LIMIT :limite OFFSET :salto",
        autor=usuario_id, estado=estado, limite=datos.POR_PAGINA,
        salto=(pagina - 1) * datos.POR_PAGINA,
    )
    for solicitud in solicitudes:
        solicitud["coincidencias"] = len(coincidencias_de(solicitud))
    return {"solicitudes": solicitudes, "total": total, "pagina": pagina, "paginas": paginas,
            "estado": estado}


def cerrar(solicitud_id: int, usuario_id: int):
    datos._estudiante(usuario_id)
    with db.transaccion():
        if not db.bloquear_fila("solicitudes", solicitud_id):
            raise LookupError("No existe la búsqueda.")
        solicitud = obtener(solicitud_id)
        if solicitud["autor_id"] != usuario_id:
            raise PermissionError("Solo el autor puede cerrar su búsqueda.")
        db.execute("UPDATE solicitudes SET estado = 'cerrada' WHERE id = :id", id=solicitud_id)
