import re
from datetime import datetime

from davincihub import db
from davincihub.utiles import ahora, fecha_corta

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


class ErrorReserva(ValueError):
    """Error base para reservas de espacios."""


class ErrorSuperposicionReserva(ErrorReserva):
    """Indica que la reserva solicitada se superpone con otra ya confirmada."""


class ErrorHorarioInvalido(ErrorReserva):
    """Indica que la reserva está fuera del horario habilitado del espacio o en el pasado."""


class ErrorCancelacionInvalida(ErrorReserva):
    """Indica que la reserva no puede cancelarse (ej. ya inició o no pertenece al usuario)."""


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
        dia = item.get("dia_semana")
        if dia is None or not isinstance(dia, int) or dia not in DIAS_SEMANA:
            raise ErrorFranjaHoraria(
                f"Día de la semana inválido: {dia}. Debe ser un entero entre 0 (Lunes) y 6 (Domingo)."
            )
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

    if capacidad is not None and (not isinstance(capacidad, int) or capacidad <= 0):
        raise ErrorEspacio("La capacidad debe ser un número entero mayor a 0.")

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

    if capacidad is not None and (not isinstance(capacidad, int) or capacidad <= 0):
        raise ErrorEspacio("La capacidad debe ser un número entero mayor a 0.")

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


def listar_espacios_catalogo() -> list[dict]:
    """Catálogo para estudiantes: solo espacios activos con sus horarios por día."""
    espacios = db.query(
        "SELECT id, nombre, descripcion, capacidad, activo"
        " FROM espacios WHERE activo = 1 ORDER BY nombre"
    )
    for esp in espacios:
        horarios = obtener_horarios_espacio(esp["id"])
        esp["horarios"] = horarios
        esp["horarios_por_dia"] = _agrupar_horarios_por_dia(horarios)
    return espacios


def listar_espacios_admin() -> list[dict]:
    """Listado para administración: incluye espacios activos y deshabilitados con sus horarios."""
    espacios = db.query(
        "SELECT id, nombre, descripcion, capacidad, activo"
        " FROM espacios ORDER BY activo DESC, nombre"
    )
    for esp in espacios:
        horarios = obtener_horarios_espacio(esp["id"])
        esp["horarios"] = horarios
        esp["horarios_por_dia"] = _agrupar_horarios_por_dia(horarios)
    return espacios


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
    if dia_semana not in DIAS_SEMANA:
        raise ErrorFranjaHoraria(
            f"Día de la semana inválido: {dia_semana}. Debe ser entre 0 y 6."
        )
    abre_val, cierra_val = validar_franja(abre, cierra)

    with db.transaccion():
        espacio = db.query_one("SELECT id FROM espacios WHERE id = :id", id=espacio_id)
        if not espacio:
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
        espacio = db.query_one("SELECT id FROM espacios WHERE id = :id", id=espacio_id)
        if not espacio:
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


# --- Operaciones de Reservas (RF-29 / D2) ---


def _validar_fechas_reserva(inicio: str, fin: str) -> tuple[datetime, datetime]:
    """Parsea y valida los timestamps ISO de una reserva."""
    try:
        dt_ini = datetime.fromisoformat(inicio)
        dt_fin = datetime.fromisoformat(fin)
    except (ValueError, TypeError) as error:
        raise ErrorHorarioInvalido("Formato de fecha u hora inválido. Usá ISO (YYYY-MM-DDTHH:MM).") from error

    if dt_ini >= dt_fin:
        raise ErrorHorarioInvalido("La hora de finalización debe ser posterior a la de inicio.")

    if dt_ini.date() != dt_fin.date():
        raise ErrorHorarioInvalido("La reserva debe iniciar y terminar en el mismo día.")

    return dt_ini, dt_fin


def verificar_horario_espacio(espacio_id: int, dt_ini: datetime, dt_fin: datetime) -> None:
    """Verifica que la reserva esté completamente dentro de al menos una franja habilitada del espacio para ese día."""
    dia_semana = dt_ini.weekday()  # 0 = lunes, 6 = domingo
    hora_ini = dt_ini.strftime("%H:%M")
    hora_fin = dt_fin.strftime("%H:%M")

    # Debe existir al menos una franja habilitada donde abre <= hora_ini AND cierra >= hora_fin
    franja = db.query_one(
        "SELECT id, abre, cierra FROM horarios_espacios"
        " WHERE espacio_id = :espacio_id AND dia_semana = :dia"
        "   AND abre <= :ini AND cierra >= :fin",
        espacio_id=espacio_id,
        dia=dia_semana,
        ini=hora_ini,
        fin=hora_fin,
    )
    if not franja:
        dia_nombre = DIAS_SEMANA.get(dia_semana, "")
        raise ErrorHorarioInvalido(
            f"El horario solicitado ({hora_ini} - {hora_fin}) está fuera de las franjas "
            f"habilitadas del espacio los {dia_nombre}."
        )


def crear_reserva(
    espacio_id: int,
    usuario_id: int,
    inicio: str,
    fin: str,
) -> int:
    """Crea y confirma una reserva para un usuario si el espacio está disponible.

    Reglas de negocio aplicadas:
    - Un espacio deshabilitado no admite reservas nuevas.
    - No se reserva en el pasado ni fuera del horario del espacio.
    - No puede haber dos reservas confirmadas que se superpongan en el mismo espacio,
      incluso con intentos concurrentes (atómico con with db.transaccion()).
    - Emite una notificación al estudiante si el servicio de notificaciones está disponible.
    """
    dt_ini, dt_fin = _validar_fechas_reserva(inicio, fin)

    momento_actual = datetime.fromisoformat(ahora())
    # Normalizar zonas horarias si alguna tiene tzinfo y la otra no
    if dt_ini.tzinfo is not None and momento_actual.tzinfo is None:
        momento_actual = momento_actual.replace(tzinfo=dt_ini.tzinfo)
    elif dt_ini.tzinfo is None and momento_actual.tzinfo is not None:
        dt_ini_cmp = dt_ini.replace(tzinfo=momento_actual.tzinfo)
    else:
        dt_ini_cmp = dt_ini

    if dt_ini_cmp < momento_actual:
        raise ErrorHorarioInvalido("No se puede reservar en el pasado.")

    with db.transaccion():
        espacio = db.query_one("SELECT id, nombre, activo FROM espacios WHERE id = :id", id=espacio_id)
        if not espacio:
            raise ErrorEspacio(f"No existe el espacio con id {espacio_id}.")
        if not espacio["activo"]:
            raise ErrorEspacio("El espacio está deshabilitado y no admite nuevas reservas.")

        # Verificar que encaje en los horarios del espacio
        verificar_horario_espacio(espacio_id, dt_ini, dt_fin)

        # Control de superposición con reservas confirmadas existentes:
        # Dos intervalos [I1, F1) e [I2, F2) se superponen si inicio < fin_existente AND fin > inicio_existente
        iso_ini = dt_ini.isoformat(timespec="seconds")
        iso_fin = dt_fin.isoformat(timespec="seconds")

        solapada = db.query_one(
            "SELECT id, inicio, fin FROM reservas"
            " WHERE espacio_id = :espacio_id AND estado = 'confirmada'"
            "   AND inicio < :fin AND fin > :ini",
            espacio_id=espacio_id,
            fin=iso_fin,
            ini=iso_ini,
        )
        if solapada:
            raise ErrorSuperposicionReserva(
                f"El espacio ya está reservado en ese horario ({solapada['inicio']} - {solapada['fin']})."
            )

        fila = db.query_one(
            "INSERT INTO reservas (espacio_id, usuario_id, inicio, fin, estado, creado)"
            " VALUES (:espacio_id, :usuario_id, :inicio, :fin, 'confirmada', :creado)"
            " RETURNING id",
            espacio_id=espacio_id,
            usuario_id=usuario_id,
            inicio=iso_ini,
            fin=iso_fin,
            creado=ahora(),
        )
        reserva_id = fila["id"]

    from davincihub.notificaciones import notificar

    notificar(
        usuario_id,
        "reservas",
        f"Tu reserva de '{espacio['nombre']}' ({fecha_corta(iso_ini)}) quedó confirmada.",
        f"/reservas/{reserva_id}",
    )

    return reserva_id


def cancelar_reserva(reserva_id: int, usuario_id: int) -> bool:
    """Cancela una reserva propia que aún no haya comenzado.

    Reglas de negocio:
    - Sólo se cancela una reserva propia que no comenzó.
    - Queda registrada como cancelada (RF-21, RN-10).
    - Notifica al estudiante sobre la cancelación.
    """
    with db.transaccion():
        reserva = db.query_one(
            "SELECT r.*, e.nombre AS espacio_nombre FROM reservas r"
            " JOIN espacios e ON e.id = r.espacio_id"
            " WHERE r.id = :id",
            id=reserva_id,
        )
        if not reserva:
            raise ErrorReserva(f"No existe la reserva #{reserva_id}.")

        if reserva["usuario_id"] != usuario_id:
            raise ErrorCancelacionInvalida("No podés cancelar una reserva que no es tuya.")

        if reserva["estado"] == "cancelada":
            raise ErrorCancelacionInvalida("La reserva ya se encuentra cancelada.")

        dt_inicio = datetime.fromisoformat(reserva["inicio"])
        momento_actual = datetime.fromisoformat(ahora())
        if dt_inicio.tzinfo is not None and momento_actual.tzinfo is None:
            momento_actual = momento_actual.replace(tzinfo=dt_inicio.tzinfo)
        elif dt_inicio.tzinfo is None and momento_actual.tzinfo is not None:
            dt_inicio = dt_inicio.replace(tzinfo=momento_actual.tzinfo)

        if dt_inicio <= momento_actual:
            raise ErrorCancelacionInvalida("No podés cancelar una reserva que ya comenzó o finalizó.")

        db.execute(
            "UPDATE reservas SET estado = 'cancelada' WHERE id = :id",
            id=reserva_id,
        )

    from davincihub.notificaciones import notificar

    notificar(
        usuario_id,
        "reservas",
        f"Tu reserva de '{reserva['espacio_nombre']}' ({fecha_corta(reserva['inicio'])}) fue cancelada.",
        "/reservas/mis-reservas",
    )

    return True


def obtener_reserva(reserva_id: int) -> dict | None:
    """Obtiene una reserva con los datos del espacio y del usuario."""
    return db.query_one(
        "SELECT r.*, e.nombre AS espacio_nombre, e.capacidad AS espacio_capacidad,"
        "       u.nombre AS usuario_nombre, u.apellido AS usuario_apellido, u.email AS usuario_email"
        " FROM reservas r"
        " JOIN espacios e ON e.id = r.espacio_id"
        " JOIN usuarios u ON u.id = r.usuario_id"
        " WHERE r.id = :id",
        id=reserva_id,
    )


def listar_reservas_usuario(usuario_id: int, solo_futuras: bool = False) -> list[dict]:
    """Lista las reservas de un usuario, con opción de filtrar solo las futuras/vigentes."""
    sql = (
        "SELECT r.*, e.nombre AS espacio_nombre, e.capacidad AS espacio_capacidad"
        " FROM reservas r"
        " JOIN espacios e ON e.id = r.espacio_id"
        " WHERE r.usuario_id = :usuario"
    )
    params = {"usuario": usuario_id}
    if solo_futuras:
        sql += " AND r.fin >= :ahora AND r.estado = 'confirmada' ORDER BY r.inicio ASC"
        params["ahora"] = ahora()
    else:
        sql += " ORDER BY r.inicio DESC"

    reservas = db.query(sql, **params)
    momento_actual = ahora()
    for r in reservas:
        r["puede_cancelar"] = bool(r["estado"] == "confirmada" and r["inicio"] > momento_actual)
    return reservas


def listar_todas_las_reservas(espacio_id: int | None = None) -> list[dict]:
    """Lista todas las reservas para administración (de un espacio o de todos)."""
    sql = (
        "SELECT r.*, e.nombre AS espacio_nombre, u.nombre AS usuario_nombre,"
        "       u.apellido AS usuario_apellido, u.email AS usuario_email"
        " FROM reservas r"
        " JOIN espacios e ON e.id = r.espacio_id"
        " JOIN usuarios u ON u.id = r.usuario_id"
    )
    params = {}
    if espacio_id is not None:
        sql += " WHERE r.espacio_id = :espacio"
        params["espacio"] = espacio_id
    sql += " ORDER BY r.inicio DESC"
    return db.query(sql, **params)


def obtener_disponibilidad_dia(espacio_id: int, fecha_str: str) -> dict:
    """Dado un espacio y una fecha (YYYY-MM-DD), retorna los horarios de apertura y las reservas confirmadas del día.

    Permite que el estudiante vea fácilmente qué franjas están libres u ocupadas.
    """
    try:
        fecha_obj = datetime.strptime(fecha_str.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError) as error:
        raise ErrorHorarioInvalido("Fecha inválida. Usá formato YYYY-MM-DD.") from error

    dia_semana = fecha_obj.weekday()
    espacio = obtener_espacio(espacio_id)
    if not espacio:
        raise ErrorEspacio(f"No existe el espacio con id {espacio_id}.")

    horarios_dia = [h for h in espacio.get("horarios", []) if h["dia_semana"] == dia_semana]

    inicio_dia = f"{fecha_str}T00:00:00"
    fin_dia = f"{fecha_str}T23:59:59"

    reservas = db.query(
        "SELECT id, inicio, fin, estado FROM reservas"
        " WHERE espacio_id = :espacio_id AND estado = 'confirmada'"
        "   AND inicio <= :fin_dia AND fin >= :inicio_dia"
        " ORDER BY inicio ASC",
        espacio_id=espacio_id,
        inicio_dia=inicio_dia,
        fin_dia=fin_dia,
    )

    return {
        "espacio": espacio,
        "fecha": fecha_str,
        "dia_nombre": DIAS_SEMANA[dia_semana],
        "horarios_habilitados": horarios_dia,
        "reservas_ocupadas": reservas,
        "abierto": len(horarios_dia) > 0,
    }
