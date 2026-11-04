from davincihub import comision, db
from davincihub.utiles import sin_acentos

LIMITE_NOMBRE = 120
LIMITE_TITULO = 160
DURACION_MAXIMA = 6


class ErrorAcademico(ValueError):
    """Error base para la gestión de carreras y materias."""


class ErrorPlan(ErrorAcademico):
    """Error en las materias del plan, no en los datos generales de la carrera."""


def listar_carreras() -> list[dict]:
    return db.query(
        "SELECT c.*,"
        " (SELECT count(*) FROM materias m WHERE m.carrera_id = c.id AND m.activa = 1) AS materias,"
        " (SELECT count(*) FROM usuarios u WHERE u.carrera_id = c.id) AS estudiantes"
        " FROM carreras c ORDER BY c.nombre"
    )


def carreras_activas() -> list[dict]:
    return db.query("SELECT id, nombre FROM carreras WHERE activa = 1 ORDER BY nombre")


def materias_activas(carrera_id: int) -> list[dict]:
    return db.query(
        "SELECT id, nombre, cuatrimestre FROM materias WHERE carrera_id = :c AND activa = 1"
        " ORDER BY cuatrimestre, nombre",
        c=carrera_id,
    )


def obtener_carrera(carrera_id: int) -> dict | None:
    return db.query_one("SELECT * FROM carreras WHERE id = :id", id=carrera_id)


def obtener_materia(materia_id: int) -> dict | None:
    return db.query_one("SELECT * FROM materias WHERE id = :id", id=materia_id)


def _texto(valor, campo: str, limite: int, obligatorio: bool = True) -> str | None:
    texto = (valor or "").strip()
    if not texto:
        if obligatorio:
            raise ErrorAcademico(f"Completá el {campo}.")
        return None
    if len(texto) > limite:
        raise ErrorAcademico(f"El {campo} admite hasta {limite} caracteres.")
    return texto


def _entero(valor, minimo: int, maximo: int, mensaje: str) -> int:
    texto = str(valor or "").strip()
    if not texto.isdecimal() or not minimo <= int(texto) <= maximo:
        raise ErrorAcademico(mensaje)
    return int(texto)


def guardar_carrera(formulario, carrera_id: int | None = None) -> int:
    nombre = _texto(formulario.get("nombre"), "nombre de la carrera", LIMITE_NOMBRE)
    titulo = _texto(formulario.get("titulo"), "título", LIMITE_TITULO, obligatorio=False)
    duracion = _entero(formulario.get("duracion_anios"), 1, DURACION_MAXIMA,
                       f"La duración tiene que ser entre 1 y {DURACION_MAXIMA} años.")
    codigo = comision.normalizar(formulario.get("codigo"))
    if codigo and not comision.PATRON_CODIGO.fullmatch(codigo):
        raise ErrorAcademico("El código de comisión son dos letras, por ejemplo AC o DW.")
    with db.transaccion():
        otras = [c for c in db.query("SELECT id, nombre, codigo FROM carreras") if c["id"] != carrera_id]
        for otra in otras:
            if sin_acentos(otra["nombre"]) == sin_acentos(nombre):
                raise ErrorAcademico(f"Ya existe la carrera «{otra['nombre']}».")
            if codigo and otra["codigo"] == codigo:
                raise ErrorAcademico(f"El código {codigo} ya es de «{otra['nombre']}».")
        actual = obtener_carrera(carrera_id) if carrera_id is not None else None
        anterior = actual["codigo"] if actual else None
        codigo = codigo or anterior or comision.codigo_sugerido(nombre, {c["codigo"] for c in otras if c["codigo"]})
        if carrera_id is None:
            fila = db.query_one(
                "INSERT INTO carreras (nombre, titulo, duracion_anios, codigo) VALUES (:n, :t, :d, :c) RETURNING id",
                n=nombre, t=titulo, d=duracion, c=codigo,
            )
            return fila["id"]
        if not db.bloquear_fila("carreras", carrera_id):
            raise ErrorAcademico("La carrera no existe.")
        ultimo = db.query_one("SELECT max(cuatrimestre) AS c FROM materias WHERE carrera_id = :id", id=carrera_id)["c"]
        if ultimo and ultimo > duracion * 2:
            raise ErrorAcademico(
                f"Hay materias en el cuatrimestre {ultimo}: movelas antes de acortar la carrera a {duracion} años."
            )
        anio = db.query_one(
            "SELECT max(anio) AS a FROM usuarios WHERE carrera_id = :id AND rol = 'estudiante'", id=carrera_id
        )["a"]
        if anio and anio > duracion:
            raise ErrorAcademico(f"Hay estudiantes en {anio}.º año: no se puede acortar la carrera a {duracion} años.")
        db.execute(
            "UPDATE carreras SET nombre = :n, titulo = :t, duracion_anios = :d, codigo = :c WHERE id = :id",
            n=nombre, t=titulo, d=duracion, c=codigo, id=carrera_id,
        )
        if anterior != codigo:
            db.execute(
                "UPDATE usuarios SET comision = :c || substr(comision, 3)"
                " WHERE carrera_id = :id AND rol = 'estudiante' AND comision IS NOT NULL",
                c=codigo, id=carrera_id,
            )
        return carrera_id


def crear_carrera_con_plan(formulario, materias: dict[int, list[str]]) -> int:
    """Crea la carrera y todas sus materias juntas: si algo falla, no queda nada a medias."""
    with db.transaccion():
        carrera_id = guardar_carrera(formulario)
        for cuatrimestre, nombres in sorted(materias.items()):
            for nombre in nombres:
                if not nombre.strip():
                    continue
                try:
                    guardar_materia(carrera_id, {"nombre": nombre, "cuatrimestre": cuatrimestre})
                except ErrorAcademico as error:
                    raise ErrorPlan(f"«{nombre.strip()}»: {error}") from error
        return carrera_id


def cambiar_estado_carrera(carrera_id: int, activa: bool) -> None:
    db.execute("UPDATE carreras SET activa = :a WHERE id = :id", a=int(activa), id=carrera_id)


def guardar_materia(carrera_id: int, formulario, materia_id: int | None = None) -> int:
    nombre = _texto(formulario.get("nombre"), "nombre de la materia", LIMITE_NOMBRE)
    with db.transaccion():
        carrera = obtener_carrera(carrera_id)
        if carrera is None:
            raise ErrorAcademico("La carrera no existe.")
        ultimo = (carrera["duracion_anios"] or DURACION_MAXIMA) * 2
        cuatrimestre = _entero(formulario.get("cuatrimestre"), 1, ultimo,
                               f"Elegí un cuatrimestre entre 1 y {ultimo}.")
        for otra in db.query("SELECT id, nombre FROM materias WHERE carrera_id = :c", c=carrera_id):
            if otra["id"] != materia_id and sin_acentos(otra["nombre"]) == sin_acentos(nombre):
                raise ErrorAcademico(f"Ya existe «{otra['nombre']}» en {carrera['nombre']}.")
        if materia_id is None:
            fila = db.query_one(
                "INSERT INTO materias (carrera_id, nombre, cuatrimestre) VALUES (:c, :n, :q) RETURNING id",
                c=carrera_id, n=nombre, q=cuatrimestre,
            )
            return fila["id"]
        db.execute(
            "UPDATE materias SET nombre = :n, cuatrimestre = :q WHERE id = :id",
            n=nombre, q=cuatrimestre, id=materia_id,
        )
        return materia_id


def cambiar_estado_materia(materia_id: int, activa: bool) -> None:
    db.execute("UPDATE materias SET activa = :a WHERE id = :id", a=int(activa), id=materia_id)


def plan_de_carrera(carrera_id: int) -> list[dict]:
    """Todas las materias (también las deshabilitadas) por año y cuatrimestre, con los cuatrimestres vacíos."""
    carrera = obtener_carrera(carrera_id)
    materias = db.query(
        "SELECT * FROM materias WHERE carrera_id = :c ORDER BY cuatrimestre, nombre", c=carrera_id
    )
    cuatrimestres = max([(carrera["duracion_anios"] or 1) * 2] + [m["cuatrimestre"] or 1 for m in materias])
    plan = []
    for numero in range(1, cuatrimestres + 1):
        if numero % 2:
            plan.append({"anio": (numero + 1) // 2, "cuatrimestres": []})
        plan[-1]["cuatrimestres"].append(
            {"numero": numero, "materias": [m for m in materias if (m["cuatrimestre"] or 1) == numero]}
        )
    return plan
