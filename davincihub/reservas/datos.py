import re

from davincihub import db

DIAS_SEMANA = {
    0: "Lunes",
    1: "Martes",
    2: "Miércoles",
    3: "Jueves",
    4: "Viernes",
    5: "Sábado",
    6: "Domingo",
}

_FORMATO_HORA = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class ErrorEspacio(ValueError):
    """Error base para operaciones sobre espacios y recursos."""


class ErrorFranjaHoraria(ErrorEspacio):
    """Error en los horarios o franjas horarias de un espacio."""


class ErrorSuperposicionHoraria(ErrorFranjaHoraria):
    """Indica que una franja horaria se superpone con otra existente."""


def _entero(valor, mensaje: str, error: type[ErrorEspacio] = ErrorEspacio) -> int:
    if isinstance(valor, bool):
        raise error(mensaje)
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and valor.strip().isdecimal():
        return int(valor.strip())
    raise error(mensaje)


def _dia_semana(valor) -> int:
    mensaje = f"Día de la semana inválido: {valor}. Debe ser un entero entre 0 (Lunes) y 6 (Domingo)."
    dia = _entero(valor, mensaje, ErrorFranjaHoraria)
    if dia not in DIAS_SEMANA:
        raise ErrorFranjaHoraria(mensaje)
    return dia


def _capacidad(valor) -> int | None:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    capacidad = _entero(valor, "La capacidad debe ser un número entero mayor a 0.")
    if capacidad <= 0:
        raise ErrorEspacio("La capacidad debe ser un número entero mayor a 0.")
    return capacidad


def validar_formato_hora(hora: str) -> str:
    """Valida y limpia una hora con formato HH:MM (24 horas)."""
    if not isinstance(hora, str):
        raise ErrorFranjaHoraria("La hora debe ser una cadena de texto.")
    hora_limpia = hora.strip()
    if not _FORMATO_HORA.match(hora_limpia):
        raise ErrorFranjaHoraria(
            f"Hora inválida '{hora}'. Usá el formato HH:MM de 24 horas (ej. 09:00 o 18:30)."
        )
    return hora_limpia


def validar_franja(abre: str, cierra: str) -> tuple[str, str]:
    """Valida formato y asegura que la hora de cierre sea posterior a la de apertura."""
    abre_val = validar_formato_hora(abre)
    cierra_val = validar_formato_hora(cierra)
    if abre_val >= cierra_val:
        raise ErrorFranjaHoraria(
            f"La hora de cierre ({cierra_val}) debe ser posterior a la de apertura ({abre_val})."
        )
    return abre_val, cierra_val


def hay_superposicion(abre1: str, cierra1: str, abre2: str, cierra2: str) -> bool:
    """Determina si dos franjas [abre1, cierra1) y [abre2, cierra2) se superponen.

    Dos franjas consecutivas (ej. 09:00-12:00 y 12:00-15:00) no se superponen.
    """
    return max(abre1, abre2) < min(cierra1, cierra2)


def validar_lista_franjas(franjas: list[dict]) -> list[dict]:
    """Valida una lista de franjas horarias y verifica que no existan superposiciones en un mismo día."""
    franjas_validadas = []
    por_dia: dict[int, list[tuple[str, str]]] = {}

    for item in franjas:
        dia = _dia_semana(item.get("dia_semana"))
        abre, cierra = validar_franja(item.get("abre", ""), item.get("cierra", ""))

        # Verificar contra franjas ya acumuladas para este mismo día
        for exist_abre, exist_cierra in por_dia.get(dia, []):
            if hay_superposicion(abre, cierra, exist_abre, exist_cierra):
                dia_nombre = DIAS_SEMANA[dia]
                raise ErrorSuperposicionHoraria(
                    f"Las franjas {abre}-{cierra} y {exist_abre}-{exist_cierra} se superponen el {dia_nombre}."
                )

        por_dia.setdefault(dia, []).append((abre, cierra))
        franjas_validadas.append(
            {
                "dia_semana": dia,
                "abre": abre,
                "cierra": cierra,
            }
        )

    return franjas_validadas


# --- Operaciones sobre Espacios ---


def crear_espacio(
    nombre: str,
    descripcion: str | None = None,
    capacidad: int | None = None,
    activo: int = 1,
) -> int:
    """Crea un nuevo espacio o recurso en el catálogo.

    Respeta las convenciones del equipo:
    - Sin id explícito (GENERATED ALWAYS).
    - RETURNING id con db.query_one.
    """
    nom = (nombre or "").strip()
    if not nom:
        raise ErrorEspacio("El nombre del espacio es obligatorio.")

    desc = descripcion.strip() if descripcion else None

    capacidad = _capacidad(capacidad)

    if activo not in (0, 1):
        raise ErrorEspacio("El estado 'activo' debe ser 0 o 1.")

    try:
        fila = db.query_one(
            "INSERT INTO espacios (nombre, descripcion, capacidad, activo)"
            " VALUES (:nombre, :descripcion, :capacidad, :activo) RETURNING id",
            nombre=nom,
            descripcion=desc,
            capacidad=capacidad,
            activo=activo,
        )
    except db.ErrorIntegridad as error:
        raise ErrorEspacio(f"Ya existe un espacio con el nombre '{nom}'.") from error

    return fila["id"]


def actualizar_espacio(
    espacio_id: int,
    nombre: str,
    descripcion: str | None = None,
    capacidad: int | None = None,
    activo: int | None = None,
) -> bool:
    """Actualiza los datos de un espacio existente."""
    nom = (nombre or "").strip()
    if not nom:
        raise ErrorEspacio("El nombre del espacio es obligatorio.")

    desc = descripcion.strip() if descripcion else None

    capacidad = _capacidad(capacidad)

    actual = db.query_one("SELECT id, activo FROM espacios WHERE id = :id", id=espacio_id)
    if not actual:
        raise ErrorEspacio(f"No existe el espacio con id {espacio_id}.")

    nuevo_activo = actual["activo"] if activo is None else activo
    if nuevo_activo not in (0, 1):
        raise ErrorEspacio("El estado 'activo' debe ser 0 o 1.")

    try:
        filas_afectadas = db.execute(
            "UPDATE espacios SET nombre = :nombre, descripcion = :descripcion,"
            " capacidad = :capacidad, activo = :activo WHERE id = :id",
            nombre=nom,
            descripcion=desc,
            capacidad=capacidad,
            activo=nuevo_activo,
            id=espacio_id,
        )
    except db.ErrorIntegridad as error:
        raise ErrorEspacio(f"Ya existe otro espacio con el nombre '{nom}'.") from error

    return filas_afectadas > 0


def cambiar_estado_espacio(espacio_id: int, activo: int) -> bool:
    """Habilita o deshabilita un espacio.

    Regla de negocio:
    Un espacio deshabilitado no admite reservas nuevas, pero conserva las existentes.
    """
    if activo not in (0, 1):
        raise ErrorEspacio("El estado 'activo' debe ser 0 o 1.")

    filas = db.execute(
        "UPDATE espacios SET activo = :activo WHERE id = :id",
        activo=activo,
        id=espacio_id,
    )
    if filas == 0:
        raise ErrorEspacio(f"No existe el espacio con id {espacio_id}.")
    return True


def deshabilitar_espacio(espacio_id: int) -> bool:
    """Deshabilita un espacio para que no admita nuevas reservas (conserva las existentes)."""
    return cambiar_estado_espacio(espacio_id, 0)


def habilitar_espacio(espacio_id: int) -> bool:
    """Habilita un espacio previamente deshabilitado."""
    return cambiar_estado_espacio(espacio_id, 1)


def espacio_admite_reservas(espacio_id: int) -> bool:
    """Indica si el espacio está habilitado para recibir nuevas reservas."""
    espacio = db.query_one("SELECT activo FROM espacios WHERE id = :id", id=espacio_id)
    return bool(espacio and espacio["activo"] == 1)


def obtener_espacio(espacio_id: int, incluir_horarios: bool = True) -> dict | None:
    """Obtiene los datos de un espacio por su id, opcionalmente con sus horarios."""
    espacio = db.query_one("SELECT * FROM espacios WHERE id = :id", id=espacio_id)
    if not espacio:
        return None

    if incluir_horarios:
        espacio["horarios"] = obtener_horarios_espacio(espacio_id)
        espacio["horarios_por_dia"] = _agrupar_horarios_por_dia(espacio["horarios"])

    return espacio


def _agrupar_horarios_por_dia(horarios: list[dict]) -> dict[int, list[dict]]:
    """Agrupa una lista de horarios por su día de la semana (0 a 6)."""
    agrupados: dict[int, list[dict]] = {dia: [] for dia in DIAS_SEMANA}
    for h in horarios:
        dia = h["dia_semana"]
        if dia in agrupados:
            agrupados[dia].append(h)
    return agrupados


def _con_horarios(espacios: list[dict]) -> list[dict]:
    """Agrega los horarios a cada espacio con una sola consulta."""
    por_espacio: dict[int, list[dict]] = {}
    if espacios:
        todos = db.query(
            "SELECT id, espacio_id, dia_semana, abre, cierra FROM horarios_espacios"
            " ORDER BY dia_semana ASC, abre ASC"
        )
        for h in todos:
            h["dia_nombre"] = DIAS_SEMANA.get(h["dia_semana"], "")
            por_espacio.setdefault(h["espacio_id"], []).append(h)
    for esp in espacios:
        esp["horarios"] = por_espacio.get(esp["id"], [])
        esp["horarios_por_dia"] = _agrupar_horarios_por_dia(esp["horarios"])
    return espacios


def listar_espacios_catalogo() -> list[dict]:
    """Catálogo para estudiantes: solo espacios activos con sus horarios por día."""
    espacios = db.query(
        "SELECT id, nombre, descripcion, capacidad, activo"
        " FROM espacios WHERE activo = 1 ORDER BY nombre"
    )
    return _con_horarios(espacios)


def listar_espacios_admin() -> list[dict]:
    """Listado para administración: incluye espacios activos y deshabilitados con sus horarios."""
    espacios = db.query(
        "SELECT id, nombre, descripcion, capacidad, activo"
        " FROM espacios ORDER BY activo DESC, nombre"
    )
    return _con_horarios(espacios)


# --- Operaciones sobre Horarios de Espacios ---


def obtener_horarios_espacio(espacio_id: int) -> list[dict]:
    """Retorna los horarios definidos para un espacio ordenados por día y hora de apertura."""
    horarios = db.query(
        "SELECT id, espacio_id, dia_semana, abre, cierra"
        " FROM horarios_espacios WHERE espacio_id = :espacio_id"
        " ORDER BY dia_semana ASC, abre ASC",
        espacio_id=espacio_id,
    )
    for h in horarios:
        h["dia_nombre"] = DIAS_SEMANA.get(h["dia_semana"], "")
    return horarios


def agregar_franja_horaria(espacio_id: int, dia_semana: int, abre: str, cierra: str) -> int:
    """Agrega una franja horaria a un espacio de manera atómica.

    Reglas de negocio:
    - La hora de cierre es posterior a la de apertura (abre < cierra).
    - Las franjas de un mismo día no se superponen.
    - Se ejecuta dentro de with db.transaccion() para evitar condiciones de carrera.
    """
    dia_semana = _dia_semana(dia_semana)
    abre_val, cierra_val = validar_franja(abre, cierra)

    with db.transaccion():
        if not db.bloquear_fila("espacios", espacio_id):
            raise ErrorEspacio(f"No existe el espacio con id {espacio_id}.")

        # Chequeo de superposición en base de datos para el mismo espacio y día:
        # Dos intervalos [A1, C1) y [A2, C2) se superponen si abre < existente.cierra AND cierra > existente.abre
        superpuesto = db.query_one(
            "SELECT id, abre, cierra FROM horarios_espacios"
            " WHERE espacio_id = :espacio_id AND dia_semana = :dia_semana"
            "   AND abre < :cierra AND cierra > :abre",
            espacio_id=espacio_id,
            dia_semana=dia_semana,
            abre=abre_val,
            cierra=cierra_val,
        )
        if superpuesto:
            dia_nombre = DIAS_SEMANA[dia_semana]
            raise ErrorSuperposicionHoraria(
                f"La franja {abre_val}-{cierra_val} se superpone con el horario existente "
                f"{superpuesto['abre']}-{superpuesto['cierra']} del día {dia_nombre}."
            )

        fila = db.query_one(
            "INSERT INTO horarios_espacios (espacio_id, dia_semana, abre, cierra)"
            " VALUES (:espacio_id, :dia_semana, :abre, :cierra) RETURNING id",
            espacio_id=espacio_id,
            dia_semana=dia_semana,
            abre=abre_val,
            cierra=cierra_val,
        )
        return fila["id"]


def eliminar_franja_horaria(horario_id: int) -> bool:
    """Elimina una franja horaria por su id."""
    filas = db.execute("DELETE FROM horarios_espacios WHERE id = :id", id=horario_id)
    return filas > 0


def reemplazar_horarios_espacio(espacio_id: int, franjas: list[dict]) -> None:
    """Reemplaza atómicamente todos los horarios de un espacio por un nuevo conjunto de franjas.

    Valida que no existan superposiciones en ningún día antes de modificar la base.
    """
    franjas_validadas = validar_lista_franjas(franjas)

    with db.transaccion():
        if not db.bloquear_fila("espacios", espacio_id):
            raise ErrorEspacio(f"No existe el espacio con id {espacio_id}.")

        db.execute("DELETE FROM horarios_espacios WHERE espacio_id = :espacio_id", espacio_id=espacio_id)

        for f in franjas_validadas:
            db.execute(
                "INSERT INTO horarios_espacios (espacio_id, dia_semana, abre, cierra)"
                " VALUES (:espacio_id, :dia_semana, :abre, :cierra)",
                espacio_id=espacio_id,
                dia_semana=f["dia_semana"],
                abre=f["abre"],
                cierra=f["cierra"],
            )
