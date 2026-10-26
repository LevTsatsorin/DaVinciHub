from davincihub import db, seguridad
from davincihub.notificaciones import notificar
from davincihub.utiles import ahora, sin_acentos

LIMITE_TITULO = 160
LIMITE_CUERPO = 5000
MINIMO_TEXTO = 10


class ErrorForo(ValueError):
    """Error de validación o estado de una acción del foro."""


class SinPermisoForo(PermissionError):
    """La persona no tiene permiso para realizar la acción del foro."""


_INVISIBLES = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"))


def _texto(valor: str | None, nombre: str, limite: int, minimo: int = 1) -> str:
    texto = (valor or "").translate(_INVISIBLES).strip()
    if not texto:
        raise ErrorForo(f"Completá {nombre}.")
    if len(texto) > limite:
        raise ErrorForo(f"{nombre.capitalize()} admite hasta {limite} caracteres.")
    if len(texto) < minimo:
        raise ErrorForo(f"{nombre.capitalize()} debe tener al menos {minimo} caracteres.")
    return texto


def _materia_de_formulario(formulario) -> int:
    carrera_texto = (formulario.get("carrera_id") or "").strip()
    materia_texto = (formulario.get("materia_id") or "").strip()
    if not carrera_texto.isdecimal() or not materia_texto.isdecimal():
        raise ErrorForo("Elegí una carrera y una materia válidas.")
    fila = db.query_one(
        "SELECT m.id FROM materias m JOIN carreras c ON c.id = m.carrera_id"
        " WHERE m.id = :materia AND c.id = :carrera AND m.activa = 1 AND c.activa = 1",
        materia=int(materia_texto),
        carrera=int(carrera_texto),
    )
    if fila is None:
        raise ErrorForo("La materia no corresponde a la carrera seleccionada.")
    return fila["id"]


def materias_para_formulario() -> list[dict]:
    return db.query(
        "SELECT m.id, m.nombre, m.carrera_id, m.cuatrimestre, c.nombre AS carrera"
        " FROM materias m JOIN carreras c ON c.id = m.carrera_id"
        " WHERE m.activa = 1 AND c.activa = 1 ORDER BY c.nombre, m.cuatrimestre, m.nombre"
    )


def listar_preguntas(
    q: str = "",
    carrera_id: int | None = None,
    materia_id: int | None = None,
    autor_id: int | None = None,
    cuatrimestre: int | None = None,
) -> list[dict]:
    condiciones = []
    parametros = {}
    buscado = sin_acentos(q.strip())
    if buscado:
        expresion = db.sql_sin_acentos(
            "p.titulo || ' ' || p.cuerpo || ' ' || m.nombre || ' ' || c.nombre"
            " || ' ' || u.nombre || ' ' || u.apellido"
        )
        condiciones.append(f"{expresion} LIKE :buscado ESCAPE '\\'")
        escapado = buscado.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        parametros["buscado"] = f"%{escapado}%"
    if carrera_id is not None:
        condiciones.append("c.id = :carrera_id")
        parametros["carrera_id"] = carrera_id
    if materia_id is not None:
        condiciones.append("m.id = :materia_id")
        parametros["materia_id"] = materia_id
    if cuatrimestre is not None:
        condiciones.append("m.cuatrimestre = :cuatrimestre")
        parametros["cuatrimestre"] = cuatrimestre
    if autor_id is not None:
        condiciones.append("p.autor_id = :autor_id")
        parametros["autor_id"] = autor_id
    donde = f" WHERE {' AND '.join(condiciones)}" if condiciones else ""
    return db.query(
        "SELECT p.id, p.autor_id, p.titulo, p.cuerpo, p.creado, m.nombre AS materia,"
        " c.nombre AS carrera, u.nombre AS autor_nombre, u.apellido AS autor_apellido,"
        " COUNT(r.id) AS respuestas,"
        " COALESCE(MAX(r.aceptada), 0) AS tiene_aceptada"
        " FROM preguntas p JOIN materias m ON m.id = p.materia_id"
        " JOIN carreras c ON c.id = m.carrera_id JOIN usuarios u ON u.id = p.autor_id"
        " LEFT JOIN respuestas r ON r.pregunta_id = p.id"
        f"{donde}"
        " GROUP BY p.id, m.nombre, c.nombre, u.nombre, u.apellido"
        " ORDER BY CASE WHEN COUNT(r.id) = 0 THEN 0 ELSE 1 END, p.creado DESC, p.id DESC",
        **parametros,
    )


def obtener_pregunta(pregunta_id: int) -> dict | None:
    return db.query_one(
        "SELECT p.id, p.autor_id, p.materia_id, p.titulo, p.cuerpo, p.creado,"
        " m.nombre AS materia, m.carrera_id, c.nombre AS carrera,"
        " u.nombre AS autor_nombre, u.apellido AS autor_apellido,"
        " EXISTS (SELECT 1 FROM preguntas pa WHERE pa.id = p.id AND pa.imagen IS NOT NULL) AS tiene_imagen,"
        " (SELECT COUNT(*) FROM respuestas r WHERE r.pregunta_id = p.id) AS cantidad_respuestas,"
        " (SELECT id FROM respuestas r WHERE r.pregunta_id = p.id AND r.aceptada = 1) AS respuesta_aceptada_id"
        " FROM preguntas p JOIN materias m ON m.id = p.materia_id"
        " JOIN carreras c ON c.id = m.carrera_id JOIN usuarios u ON u.id = p.autor_id"
        " WHERE p.id = :id",
        id=pregunta_id,
    )


def listar_respuestas(pregunta_id: int, usuario_id: int) -> list[dict]:
    respuestas = db.query(
        "SELECT r.*, u.nombre AS autor_nombre, u.apellido AS autor_apellido,"
        " (SELECT COUNT(*) FROM valoraciones_respuestas v WHERE v.respuesta_id = r.id) AS utiles,"
        " EXISTS (SELECT 1 FROM valoraciones_respuestas v"
        "         WHERE v.respuesta_id = r.id AND v.usuario_id = :usuario) AS valorada_por_mi,"
        " m.nombre AS materia, m.id AS materia_id,"
        " r.respuesta_padre_id"
        " FROM respuestas r JOIN usuarios u ON u.id = r.autor_id"
        " JOIN preguntas p ON p.id = r.pregunta_id"
        " JOIN materias m ON m.id = p.materia_id"
        " WHERE r.pregunta_id = :pregunta"
        " ORDER BY r.creado ASC, r.id ASC",
        pregunta=pregunta_id,
        usuario=usuario_id,
    )
    catedras: dict[int, bool] = {}
    por_id = {respuesta["id"]: respuesta for respuesta in respuestas}
    respuestas_hijas: dict[int | None, list[dict]] = {}
    for respuesta in respuestas:
        autor_id = respuesta["autor_id"]
        if autor_id not in catedras:
            catedras[autor_id] = seguridad.es_catedra(autor_id, respuesta["materia_id"])
        respuesta["es_catedra"] = catedras[autor_id]
        respuesta["respuestas_hijas"] = []
        padre_id = respuesta["respuesta_padre_id"]
        if padre_id is not None:
            padre = por_id.get(padre_id)
            if padre is not None and padre["pregunta_id"] == pregunta_id:
                padre["respuestas_hijas"].append(respuesta)
                continue
        respuestas_hijas.setdefault(None, []).append(respuesta)

    raices = respuestas_hijas.get(None, [])
    raices.sort(key=lambda respuesta: (not bool(respuesta["aceptada"]), respuesta["creado"], respuesta["id"]))
    recorrido = []

    def agregar_hijas(respuesta: dict, nivel: int) -> None:
        for hija in respuesta["respuestas_hijas"]:
            hija["nivel"] = nivel
            recorrido.append(hija)
            agregar_hijas(hija, nivel + 1)

    for raiz in raices:
        raiz["nivel"] = 0
        recorrido.append(raiz)
        agregar_hijas(raiz, 1)
    return recorrido


def obtener_respuesta(respuesta_id: int) -> dict | None:
    return db.query_one(
        "SELECT r.*, p.autor_id AS pregunta_autor_id"
        " FROM respuestas r JOIN preguntas p ON p.id = r.pregunta_id WHERE r.id = :id",
        id=respuesta_id,
    )


def crear_pregunta(
    autor_id: int, formulario, imagen_tipo: str | None = None, imagen: bytes | None = None
) -> int:
    materia_id = _materia_de_formulario(formulario)
    titulo = _texto(formulario.get("titulo"), "el título", LIMITE_TITULO, MINIMO_TEXTO)
    cuerpo = _texto(formulario.get("cuerpo"), "la descripción", LIMITE_CUERPO, MINIMO_TEXTO)
    fila = db.query_one(
        "INSERT INTO preguntas (autor_id, materia_id, titulo, cuerpo, creado, imagen_tipo, imagen)"
        " VALUES (:autor, :materia, :titulo, :cuerpo, :creado, :imagen_tipo, :imagen) RETURNING id",
        autor=autor_id,
        materia=materia_id,
        titulo=titulo,
        cuerpo=cuerpo,
        creado=ahora(),
        imagen_tipo=imagen_tipo,
        imagen=imagen,
    )
    return fila["id"]


def editar_pregunta(
    pregunta_id: int,
    usuario_id: int,
    formulario,
    imagen_tipo: str | None = None,
    imagen: bytes | None = None,
) -> None:
    materia_id = _materia_de_formulario(formulario)
    titulo = _texto(formulario.get("titulo"), "el título", LIMITE_TITULO, MINIMO_TEXTO)
    cuerpo = _texto(formulario.get("cuerpo"), "la descripción", LIMITE_CUERPO, MINIMO_TEXTO)
    with db.transaccion():
        if not db.bloquear_fila("preguntas", pregunta_id):
            raise ErrorForo("La pregunta ya no existe.")
        pregunta = db.query_one("SELECT autor_id FROM preguntas WHERE id = :id", id=pregunta_id)
        if pregunta["autor_id"] != usuario_id:
            raise SinPermisoForo
        if db.query_one(
            "SELECT id FROM respuestas WHERE pregunta_id = :pregunta AND aceptada = 1",
            pregunta=pregunta_id,
        ):
            raise ErrorForo("No podés editar la pregunta después de aceptar una respuesta.")
        db.execute(
            "UPDATE preguntas SET materia_id = :materia, titulo = :titulo, cuerpo = :cuerpo,"
            " imagen_tipo = COALESCE(:imagen_tipo, imagen_tipo),"
            " imagen = COALESCE(:imagen, imagen)"
            " WHERE id = :id",
            materia=materia_id,
            titulo=titulo,
            cuerpo=cuerpo,
            imagen_tipo=imagen_tipo,
            imagen=imagen,
            id=pregunta_id,
        )


def crear_respuesta(
    pregunta_id: int,
    autor_id: int,
    cuerpo: str | None,
    respuesta_padre_id: int | None = None,
) -> int:
    contenido = _texto(cuerpo, "tu respuesta", LIMITE_CUERPO)
    with db.transaccion():
        if not db.bloquear_fila("preguntas", pregunta_id):
            raise ErrorForo("La pregunta ya no existe.")
        pregunta = db.query_one(
            "SELECT autor_id FROM preguntas WHERE id = :id",
            id=pregunta_id,
        )
        padre = None
        if respuesta_padre_id is not None:
            padre = obtener_respuesta(respuesta_padre_id)
            if padre is None or padre["pregunta_id"] != pregunta_id:
                raise ErrorForo("El comentario al que querés responder no existe.")
            if padre["autor_id"] == autor_id:
                raise SinPermisoForo
        fila = db.query_one(
            "INSERT INTO respuestas (pregunta_id, autor_id, cuerpo, creado, respuesta_padre_id)"
            " VALUES (:pregunta, :autor, :cuerpo, :creado, :padre) RETURNING id",
            pregunta=pregunta_id,
            autor=autor_id,
            cuerpo=contenido,
            creado=ahora(),
            padre=respuesta_padre_id,
        )
        autor = db.query_one("SELECT nombre, apellido FROM usuarios WHERE id = :id", id=autor_id)
        nombre = f"{autor['nombre']} {autor['apellido']}"
        if padre:
            notificar(padre["autor_id"], "foro", f"{nombre} respondió tu comentario.", f"/foro/preguntas/{pregunta_id}")
        if pregunta["autor_id"] not in (autor_id, padre and padre["autor_id"]):
            notificar(pregunta["autor_id"], "foro", f"{nombre} respondió tu pregunta.", f"/foro/preguntas/{pregunta_id}")
    return fila["id"]


def editar_respuesta(respuesta_id: int, usuario_id: int, cuerpo: str | None) -> None:
    contenido = _texto(cuerpo, "tu respuesta", LIMITE_CUERPO)
    respuesta = obtener_respuesta(respuesta_id)
    if respuesta is None:
        raise ErrorForo("La respuesta ya no existe.")
    with db.transaccion():
        if not db.bloquear_fila("preguntas", respuesta["pregunta_id"]):
            raise ErrorForo("La pregunta ya no existe.")
        respuesta = obtener_respuesta(respuesta_id)
        if respuesta is None:
            raise ErrorForo("La respuesta ya no existe.")
        if respuesta["autor_id"] != usuario_id:
            raise SinPermisoForo
        if db.query_one(
            "SELECT id FROM respuestas WHERE pregunta_id = :pregunta AND aceptada = 1",
            pregunta=respuesta["pregunta_id"],
        ):
            raise ErrorForo("No podés editar respuestas después de aceptar una.")
        db.execute(
            "UPDATE respuestas SET cuerpo = :cuerpo WHERE id = :id",
            cuerpo=contenido,
            id=respuesta_id,
        )


def establecer_aceptacion(respuesta_id: int, usuario_id: int, aceptar: bool) -> bool:
    respuesta = obtener_respuesta(respuesta_id)
    if respuesta is None:
        raise ErrorForo("La respuesta ya no existe.")
    with db.transaccion():
        if not db.bloquear_fila("preguntas", respuesta["pregunta_id"]):
            raise ErrorForo("La pregunta ya no existe.")
        pregunta = db.query_one(
            "SELECT autor_id FROM preguntas WHERE id = :id",
            id=respuesta["pregunta_id"],
        )
        if pregunta["autor_id"] != usuario_id:
            raise SinPermisoForo
        respuesta = obtener_respuesta(respuesta_id)
        if respuesta is None:
            raise ErrorForo("La respuesta ya no existe.")
        if aceptar and respuesta["autor_id"] == usuario_id:
            raise SinPermisoForo
        if not aceptar:
            db.execute("UPDATE respuestas SET aceptada = 0 WHERE id = :id", id=respuesta_id)
            return False
        if respuesta["aceptada"]:
            return True
        db.execute(
            "UPDATE respuestas SET aceptada = 0 WHERE pregunta_id = :pregunta AND aceptada = 1",
            pregunta=respuesta["pregunta_id"],
        )
        db.execute("UPDATE respuestas SET aceptada = 1 WHERE id = :id", id=respuesta_id)
        pregunta_id = respuesta["pregunta_id"]
        notificar(
            respuesta["autor_id"],
            "foro",
            "Tu respuesta fue aceptada.",
            f"/foro/preguntas/{pregunta_id}",
        )
    return True


def valorar_respuesta(respuesta_id: int, usuario_id: int) -> bool:
    respuesta = obtener_respuesta(respuesta_id)
    if respuesta is None:
        raise ErrorForo("La respuesta ya no existe.")
    if respuesta["autor_id"] == usuario_id:
        raise SinPermisoForo
    with db.transaccion():
        fila = db.query_one(
            "INSERT INTO valoraciones_respuestas (respuesta_id, usuario_id, valor, creado)"
            " VALUES (:respuesta, :usuario, 1, :creado)"
            " ON CONFLICT (respuesta_id, usuario_id) DO NOTHING RETURNING id",
            respuesta=respuesta_id,
            usuario=usuario_id,
            creado=ahora(),
        )
        if fila is None:
            return False
        notificar(
            respuesta["autor_id"],
            "foro",
            "Alguien marcó tu respuesta como útil.",
            f"/foro/preguntas/{respuesta['pregunta_id']}",
        )
    return True
