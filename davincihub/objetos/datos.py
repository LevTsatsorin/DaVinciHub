from decimal import Decimal, InvalidOperation

from davincihub import db
from davincihub.utiles import ahora, sin_acentos

CATEGORIAS = {
    "libros_apuntes": "Libros y apuntes",
    "dibujo_diseno": "Dibujo y diseño",
    "computacion": "Computación y accesorios",
    "foto_video": "Fotografía y video",
    "audio_iluminacion": "Audio e iluminación",
    "utiles": "Útiles y organización",
    "otros": "Otros materiales de estudio",
}
CONDICIONES = {
    "nuevo_como_nuevo": "Nuevo o como nuevo",
    "usado_buen_estado": "Usado en buen estado",
    "desgaste_visible": "Usado con desgaste visible",
}
MODALIDADES = {"venta": "Venta", "intercambio": "Intercambio", "prestamo": "Préstamo"}
ESTADOS = {"activa": "Activa", "pausada": "Pausada", "cerrada": "Cerrada"}
POR_PAGINA = 12
PRECIO_MAXIMO = Decimal("999999999.99")


class ErrorPublicacion(ValueError):
    def __init__(self, errores: dict[str, str]):
        self.errores = errores
        super().__init__(next(iter(errores.values())))


def _estudiante(usuario_id: int):
    usuario = db.query_one(
        "SELECT id FROM usuarios WHERE id = :id AND rol = 'estudiante' AND bloqueado = 0",
        id=usuario_id,
    )
    if usuario is None:
        raise PermissionError("Solo los estudiantes habilitados pueden publicar.")


def _validar(form, carrera_actual: int | None = None) -> dict:
    errores = {}
    campos = {}
    for campo, limite in (("titulo", 120), ("descripcion", 2000)):
        valor = (form.get(campo) or "").strip()
        if not valor:
            errores[campo] = "Campo obligatorio."
        elif len(valor) > limite:
            errores[campo] = f"Usá como máximo {limite} caracteres."
        campos[campo] = valor
    for campo, opciones in (
        ("categoria", CATEGORIAS), ("estado_objeto", CONDICIONES), ("modalidad", MODALIDADES)
    ):
        valor = form.get(campo) or ""
        if valor not in opciones:
            errores[campo] = "Elegí una opción válida."
        campos[campo] = valor

    campos["precio"] = None
    if campos["modalidad"] == "venta":
        try:
            texto = (form.get("precio") or "").strip()
            precio = Decimal(texto)
            if not precio.is_finite() or not 0 < precio <= PRECIO_MAXIMO:
                raise ValueError
            if precio != precio.quantize(Decimal("0.01")):
                raise ValueError
            campos["precio"] = float(precio)
        except (InvalidOperation, ValueError):
            errores["precio"] = "Ingresá un precio mayor a 0, con hasta 2 decimales (máximo $999.999.999,99)."

    campos["carrera_id"] = None
    carrera = (form.get("carrera_id") or "").strip()
    if carrera:
        try:
            if not carrera.isdecimal() or len(carrera) > 10:
                raise ValueError
            carrera_id = int(carrera)
            if not 0 < carrera_id <= 2147483647 or not db.query_one(
                "SELECT id FROM carreras WHERE id = :id AND (activa = 1 OR id = :actual)",
                id=carrera_id, actual=carrera_actual,
            ):
                raise ValueError
            campos["carrera_id"] = carrera_id
        except ValueError:
            errores["carrera_id"] = "Elegí una carrera disponible o dejá el campo vacío."
    if errores:
        raise ErrorPublicacion(errores)
    return campos


def crear(usuario_id: int, form) -> int:
    from davincihub.objetos import busquedas

    _estudiante(usuario_id)
    campos = _validar(form)
    with db.transaccion():
        fila = db.query_one(
            "INSERT INTO publicaciones (autor_id, carrera_id, titulo, descripcion, categoria,"
            " estado_objeto, modalidad, precio, creado)"
            " VALUES (:autor, :carrera_id, :titulo, :descripcion, :categoria, :estado_objeto,"
            " :modalidad, :precio, :creado) RETURNING id",
            autor=usuario_id, creado=ahora(), **campos,
        )
        busquedas.detectar_para_publicacion(fila["id"])
    return fila["id"]


def obtener(publicacion_id: int) -> dict | None:
    return db.query_one(
        "SELECT p.*, u.nombre AS autor_nombre, u.apellido AS autor_apellido,"
        " u.bloqueado AS autor_bloqueado, c.nombre AS carrera"
        " FROM publicaciones p JOIN usuarios u ON u.id = p.autor_id"
        " LEFT JOIN carreras c ON c.id = p.carrera_id WHERE p.id = :id",
        id=publicacion_id,
    )


def _propia(publicacion_id: int, usuario_id: int) -> dict:
    _estudiante(usuario_id)
    if not db.bloquear_fila("publicaciones", publicacion_id):
        raise LookupError("No existe la publicación.")
    publicacion = obtener(publicacion_id)
    if publicacion["autor_id"] != usuario_id:
        raise PermissionError("Solo el dueño puede modificar su publicación.")
    return publicacion


def editar(publicacion_id: int, usuario_id: int, form):
    from davincihub.objetos import busquedas, prestamos

    with db.transaccion():
        publicacion = _propia(publicacion_id, usuario_id)
        if publicacion["estado"] == "cerrada":
            raise ErrorPublicacion({"general": "Una publicación cerrada ya no se puede editar."})
        campos = _validar(form, publicacion["carrera_id"])
        if campos["modalidad"] != "prestamo" and prestamos.ocupado(publicacion_id):
            raise ErrorPublicacion({"general": "Registrá la devolución o cancelá el préstamo antes de cambiar la modalidad."})
        db.execute(
            "UPDATE publicaciones SET carrera_id = :carrera_id, titulo = :titulo,"
            " descripcion = :descripcion, categoria = :categoria, estado_objeto = :estado_objeto,"
            " modalidad = :modalidad, precio = :precio WHERE id = :id",
            id=publicacion_id, **campos,
        )
        busquedas.detectar_para_publicacion(publicacion_id)


def cambiar_estado(publicacion_id: int, usuario_id: int, estado: str):
    from davincihub.objetos import busquedas, prestamos

    with db.transaccion():
        publicacion = _propia(publicacion_id, usuario_id)
        if estado not in ESTADOS:
            raise ErrorPublicacion({"general": "Estado de publicación inválido."})
        if publicacion["estado"] == "cerrada":
            raise ErrorPublicacion({"general": "La publicación ya está cerrada."})
        if estado == "cerrada" and prestamos.ocupado(publicacion_id):
            raise ErrorPublicacion({"general": "Registrá la devolución o cancelá el préstamo antes de eliminar la publicación."})
        db.execute("UPDATE publicaciones SET estado = :estado WHERE id = :id",
                   estado=estado, id=publicacion_id)
        if estado == "activa":
            busquedas.detectar_para_publicacion(publicacion_id)


def carreras_disponibles(actual: int | None = None) -> list[dict]:
    return db.query(
        "SELECT id, nombre FROM carreras WHERE activa = 1 OR id = :actual ORDER BY nombre",
        actual=actual,
    )


def listar(filtros: dict, pagina: int = 1, autor_id: int | None = None,
           excluir_autor_id: int | None = None) -> dict:
    condiciones = ["p.autor_id = :autor"] if autor_id is not None else [
        "p.estado = 'activa'", "u.bloqueado = 0", "p.oculto = 0"
    ]
    params = {"autor": autor_id} if autor_id is not None else {}
    if autor_id is None and excluir_autor_id is not None:
        condiciones.append("p.autor_id != :excluir_autor")
        params["excluir_autor"] = excluir_autor_id
    if autor_id is not None and filtros.get("estado") in ESTADOS:
        condiciones.append("p.estado = :estado")
        params["estado"] = filtros["estado"]
    if filtros.get("q"):
        texto = sin_acentos(filtros["q"])
        texto = texto.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        condiciones.append(db.sql_sin_acentos("p.titulo") + " LIKE :q ESCAPE '!' ")
        params["q"] = f"%{texto}%"
    for campo in ("categoria", "modalidad", "carrera_id"):
        if filtros.get(campo):
            condiciones.append(f"p.{campo} = :{campo}")
            params[campo] = filtros[campo]
    tablas = (
        " FROM publicaciones p JOIN usuarios u ON u.id = p.autor_id"
        " LEFT JOIN carreras c ON c.id = p.carrera_id WHERE " + " AND ".join(condiciones)
    )
    total = db.query_one("SELECT count(*) AS n" + tablas, **params)["n"]
    paginas = max(1, (total + POR_PAGINA - 1) // POR_PAGINA)
    pagina = min(max(1, pagina), paginas)
    publicaciones = db.query(
        "SELECT p.*, u.nombre AS autor_nombre, u.apellido AS autor_apellido, c.nombre AS carrera"
        + tablas + " ORDER BY p.creado DESC, p.id DESC LIMIT :limite OFFSET :salto",
        limite=POR_PAGINA, salto=(pagina - 1) * POR_PAGINA, **params,
    )
    return {"publicaciones": publicaciones, "total": total, "pagina": pagina, "paginas": paginas}
