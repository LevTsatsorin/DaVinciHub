from davincihub import db
from davincihub.notificaciones import notificar
from davincihub.reservas import datos as reservas
from davincihub.utiles import ahora, ahora_local, fecha_corta

LIMITE_NOMBRE = 120
LIMITE_DESCRIPCION = 2000
LIMITE_MOTIVO = 300


class ErrorActividad(ValueError):
    """Error base para operaciones sobre actividades."""


def _texto(valor: str, campo: str, limite: int) -> str:
    texto = (valor or "").strip()
    if not texto:
        raise ErrorActividad(f"Completá {campo} de la actividad.")
    if len(texto) > limite:
        raise ErrorActividad(f"{campo[0].upper()}{campo[1:]} admite hasta {limite} caracteres.")
    return texto


def crear_actividad(
    creador_id: int,
    nombre: str,
    descripcion: str,
    espacio_id: int,
    inicio: str,
    fin: str,
    cupo_maximo: int,
    aprobada: bool = False,
) -> int:
    """Crea una actividad y reserva su espacio en la misma transacción.

    La de un estudiante queda 'pendiente'; la que crea un admin se publica directamente.

    La reserva aplica las reglas de reservas (horario del espacio, sin superposición, capacidad),
    así el espacio queda tomado mientras la escuela revisa la propuesta.
    """
    nom = _texto(nombre, "el nombre", LIMITE_NOMBRE)
    desc = _texto(descripcion, "la descripción", LIMITE_DESCRIPCION)
    if not inicio or not str(inicio).strip():
        raise ErrorActividad("Elegí a qué hora empieza la actividad.")
    if not fin or not str(fin).strip():
        raise ErrorActividad("Elegí a qué hora termina la actividad.")
    try:
        cupo = int(cupo_maximo)
        if not 0 < cupo <= reservas.MAXIMO_PERSONAS:
            raise ValueError
    except (ValueError, TypeError) as error:
        raise ErrorActividad(
            f"El cupo máximo tiene que ser un número entre 1 y {reservas.MAXIMO_PERSONAS:,}.".replace(",", ".")
        ) from error
    espacio = reservas.obtener_espacio(espacio_id)
    if espacio and espacio["capacidad"] and cupo > espacio["capacidad"]:
        raise ErrorActividad(f"El cupo supera la capacidad de {espacio['nombre']} ({espacio['capacidad']} personas).")

    try:
        with db.transaccion():
            reserva_id = reservas.crear_reserva(
                espacio_id, creador_id, inicio, fin, motivo=nom, personas=cupo, avisar=False
            )
            reserva = reservas.obtener_reserva(reserva_id)
            fila = db.query_one(
                "INSERT INTO actividades (creador_id, nombre, descripcion, inicio, fin, ubicacion, cupo_maximo,"
                " estado, reserva_id, creado)"
                " VALUES (:creador, :nombre, :descripcion, :inicio, :fin, :ubicacion, :cupo, :estado,"
                " :reserva, :creado) RETURNING id",
                creador=creador_id,
                nombre=nom,
                descripcion=desc,
                inicio=reserva["inicio"],
                fin=reserva["fin"],
                ubicacion=reserva["espacio_nombre"],
                cupo=cupo,
                reserva=reserva_id,
                estado="aprobada" if aprobada else "pendiente",
                creado=ahora(),
            )
    except (reservas.ErrorEspacio, reservas.ErrorReserva) as error:
        raise ErrorActividad(str(error)) from error
    return fila["id"]


def _actividad_pendiente(actividad_id: int) -> dict:
    if not db.bloquear_fila("actividades", actividad_id):
        raise ErrorActividad(f"No existe la actividad #{actividad_id}.")
    act = db.query_one("SELECT id, creador_id, nombre, estado FROM actividades WHERE id = :id", id=actividad_id)
    if act["estado"] != "pendiente":
        raise ErrorActividad(f"La actividad ya está en estado '{act['estado']}'.")
    return act


def aprobar_actividad(actividad_id: int) -> bool:
    """Aprueba una actividad pendiente y notifica a su creador en la misma transacción."""
    with db.transaccion():
        act = _actividad_pendiente(actividad_id)
        db.execute(
            "UPDATE actividades SET estado = 'aprobada', motivo_rechazo = NULL WHERE id = :id",
            id=actividad_id,
        )
        notificar(
            act["creador_id"],
            "actividades",
            f"Tu actividad '{act['nombre']}' fue aprobada y ya está publicada.",
            f"/actividades/{actividad_id}",
        )
    return True


def rechazar_actividad(actividad_id: int, motivo: str) -> bool:
    """Rechaza una actividad pendiente exigiendo motivo y notifica a su creador (RF-22)."""
    mot = (motivo or "").strip()
    if not mot:
        raise ErrorActividad("El motivo de rechazo es obligatorio.")
    if len(mot) > LIMITE_MOTIVO:
        raise ErrorActividad(f"El motivo admite hasta {LIMITE_MOTIVO} caracteres.")

    with db.transaccion():
        act = _actividad_pendiente(actividad_id)
        db.execute(
            "UPDATE actividades SET estado = 'rechazada', motivo_rechazo = :motivo WHERE id = :id",
            motivo=mot,
            id=actividad_id,
        )
        db.execute(
            "UPDATE reservas SET estado = 'cancelada'"
            " WHERE id = (SELECT reserva_id FROM actividades WHERE id = :id)",
            id=actividad_id,
        )
        notificar(
            act["creador_id"],
            "actividades",
            f"Tu actividad '{act['nombre']}' fue rechazada. Motivo: {mot}",
            "/actividades/mis-actividades",
        )
    return True


def obtener_actividad(actividad_id: int) -> dict | None:
    """Obtiene una actividad por su id con los datos de su creador y el conteo de inscriptos."""
    act = db.query_one(
        "SELECT a.*, u.nombre AS creador_nombre, u.apellido AS creador_apellido, u.email AS creador_email,"
        "       u.rol AS creador_rol,"
        "       (SELECT count(*) FROM inscripciones i WHERE i.actividad_id = a.id) AS inscriptos,"
        "       r.espacio_id"
        " FROM actividades a"
        " JOIN usuarios u ON u.id = a.creador_id"
        " LEFT JOIN reservas r ON r.id = a.reserva_id"
        " WHERE a.id = :id",
        id=actividad_id,
    )
    if act:
        act["inicio_formato"] = fecha_corta(act["inicio"])
        act["fin_formato"] = fecha_corta(act["fin"]) if act["fin"] else None
    return act


def _filtro_publicas(desde: str | None, hasta: str | None, excluir: int | None) -> tuple[str, dict]:
    sql = " WHERE a.estado = 'aprobada' AND COALESCE(a.fin, a.inicio) >= :ahora"
    params: dict = {"ahora": ahora_local()}
    if desde:
        sql += " AND a.inicio >= :desde"
        params["desde"] = desde
    if hasta:
        sql += " AND a.inicio < :hasta"
        params["hasta"] = hasta
    if excluir:
        sql += " AND a.id <> :excluir"
        params["excluir"] = excluir
    return sql, params


def listar_actividades_publicas(
    desde: str | None = None,
    hasta: str | None = None,
    limite: int | None = None,
    salto: int = 0,
    excluir: int | None = None,
) -> list[dict]:
    """Actividades aprobadas que todavía no terminaron (RN-11), opcionalmente de un período y paginadas."""
    filtro, params = _filtro_publicas(desde, hasta, excluir)
    sql = (
        "SELECT a.*, u.nombre AS creador_nombre, u.apellido AS creador_apellido,"
        "       (SELECT count(*) FROM inscripciones i WHERE i.actividad_id = a.id) AS inscriptos"
        " FROM actividades a"
        " JOIN usuarios u ON u.id = a.creador_id" + filtro + " ORDER BY a.inicio ASC, a.id ASC"
    )
    if limite:
        sql += " LIMIT :limite OFFSET :salto"
        params |= {"limite": limite, "salto": salto}
    filas = db.query(sql, **params)
    for act in filas:
        act["inicio_formato"] = fecha_corta(act["inicio"])
        act["fin_formato"] = fecha_corta(act["fin"]) if act["fin"] else None
    return filas


def contar_actividades_publicas(desde: str | None = None, hasta: str | None = None,
                                excluir: int | None = None) -> int:
    filtro, params = _filtro_publicas(desde, hasta, excluir)
    return db.query_one("SELECT count(*) AS n FROM actividades a" + filtro, **params)["n"]


def dias_con_actividades(desde: str, hasta: str) -> dict[str, int]:
    """Cantidad de actividades aprobadas que todavía no terminaron, por día, para el calendario."""
    filas = db.query(
        "SELECT substr(inicio, 1, 10) AS dia, count(*) AS n FROM actividades"
        " WHERE estado = 'aprobada' AND inicio >= :desde AND inicio < :hasta"
        "   AND COALESCE(fin, inicio) >= :ahora"
        " GROUP BY substr(inicio, 1, 10)",
        desde=desde,
        hasta=hasta,
        ahora=ahora_local(),
    )
    return {fila["dia"]: fila["n"] for fila in filas}


def listar_actividades_creador(creador_id: int) -> list[dict]:
    """Lista las actividades creadas por un usuario con su estado actual."""
    filas = db.query(
        "SELECT a.*,"
        "       (SELECT count(*) FROM inscripciones i WHERE i.actividad_id = a.id) AS inscriptos"
        " FROM actividades a"
        " WHERE a.creador_id = :creador"
        " ORDER BY a.creado DESC",
        creador=creador_id,
    )
    for act in filas:
        act["inicio_formato"] = fecha_corta(act["inicio"])
        act["fin_formato"] = fecha_corta(act["fin"]) if act["fin"] else None
    return filas


def listar_actividades_admin(estado: str | None = None) -> list[dict]:
    """Lista actividades para el panel de administración, opcionalmente filtrando por estado."""
    sql = (
        "SELECT a.*, u.nombre AS creador_nombre, u.apellido AS creador_apellido, u.email AS creador_email,"
        "       u.rol AS creador_rol,"
        "       (SELECT count(*) FROM inscripciones i WHERE i.actividad_id = a.id) AS inscriptos"
        " FROM actividades a"
        " JOIN usuarios u ON u.id = a.creador_id"
    )
    params = {}
    if estado:
        sql += " WHERE a.estado = :estado"
        params["estado"] = estado
    sql += " ORDER BY a.estado = 'pendiente' DESC, a.creado DESC"

    filas = db.query(sql, **params)
    for act in filas:
        act["inicio_formato"] = fecha_corta(act["inicio"])
        act["fin_formato"] = fecha_corta(act["fin"]) if act["fin"] else None
    return filas


def contar_actividades_por_estado() -> dict[str, int]:
    filas = db.query("SELECT estado, count(*) AS n FROM actividades GROUP BY estado")
    return {fila["estado"]: fila["n"] for fila in filas}


def esta_inscripto(actividad_id: int, usuario_id: int) -> bool:
    return db.query_one(
        "SELECT 1 AS si FROM inscripciones WHERE actividad_id = :a AND usuario_id = :u",
        a=actividad_id,
        u=usuario_id,
    ) is not None


def inscribir(actividad_id: int, usuario_id: int) -> None:
    """Inscribe a un estudiante sin pasarse del cupo, aunque lleguen inscripciones a la vez (RN-12, CA-08)."""
    with db.transaccion():
        if not db.bloquear_fila("actividades", actividad_id):
            raise ErrorActividad("La actividad no existe.")
        act = db.query_one(
            "SELECT id, creador_id, nombre, estado, inicio, cupo_maximo FROM actividades WHERE id = :id",
            id=actividad_id,
        )
        if act["estado"] != "aprobada":
            raise ErrorActividad("Sólo te podés inscribir en actividades aprobadas.")
        if act["creador_id"] == usuario_id:
            raise ErrorActividad("No te podés inscribir en tu propia actividad.")
        if act["inicio"] <= ahora_local():
            raise ErrorActividad("La actividad ya empezó: no admite inscripciones.")
        if esta_inscripto(actividad_id, usuario_id):
            raise ErrorActividad("Ya estás inscripto en esta actividad.")
        ocupados = db.query_one(
            "SELECT count(*) AS n FROM inscripciones WHERE actividad_id = :id", id=actividad_id
        )["n"]
        if ocupados >= act["cupo_maximo"]:
            raise ErrorActividad("La actividad está completa: no quedan lugares.")
        db.execute(
            "INSERT INTO inscripciones (actividad_id, usuario_id, creado) VALUES (:a, :u, :creado)",
            a=actividad_id,
            u=usuario_id,
            creado=ahora(),
        )
        alumno = db.query_one("SELECT nombre, apellido FROM usuarios WHERE id = :id", id=usuario_id)
        notificar(
            act["creador_id"],
            "actividades",
            f"{alumno['nombre']} {alumno['apellido']} se inscribió en '{act['nombre']}'.",
            f"/actividades/{actividad_id}/inscriptos",
        )


def dar_de_baja(actividad_id: int, usuario_id: int) -> None:
    with db.transaccion():
        if not db.bloquear_fila("actividades", actividad_id):
            raise ErrorActividad("La actividad no existe.")
        act = db.query_one("SELECT inicio FROM actividades WHERE id = :id", id=actividad_id)
        if act["inicio"] <= ahora_local():
            raise ErrorActividad("La actividad ya empezó: no te podés dar de baja.")
        if not db.execute(
            "DELETE FROM inscripciones WHERE actividad_id = :a AND usuario_id = :u", a=actividad_id, u=usuario_id
        ):
            raise ErrorActividad("No estabas inscripto en esta actividad.")


def cancelar_actividad(actividad_id: int, usuario_id: int) -> None:
    """El creador o un admin cancela la actividad: se libera el espacio y se avisa a los inscriptos."""
    with db.transaccion():
        if not db.bloquear_fila("actividades", actividad_id):
            raise ErrorActividad("La actividad no existe.")
        act = db.query_one(
            "SELECT id, creador_id, nombre, estado, inicio, reserva_id FROM actividades WHERE id = :id",
            id=actividad_id,
        )
        es_admin = db.query_one("SELECT rol FROM usuarios WHERE id = :id", id=usuario_id)["rol"] == "admin"
        if act["creador_id"] != usuario_id and not es_admin:
            raise ErrorActividad("Sólo el creador de la actividad o la escuela la pueden cancelar.")
        if act["estado"] not in ("pendiente", "aprobada"):
            raise ErrorActividad(f"La actividad ya está en estado '{act['estado']}'.")
        if act["inicio"] <= ahora_local():
            raise ErrorActividad("La actividad ya empezó: no se puede cancelar.")
        db.execute("UPDATE actividades SET estado = 'cancelada' WHERE id = :id", id=actividad_id)
        db.execute("UPDATE reservas SET estado = 'cancelada' WHERE id = :id", id=act["reserva_id"])
        for fila in listar_inscriptos(actividad_id):
            notificar(
                fila["id"],
                "actividades",
                f"La actividad '{act['nombre']}' ({fecha_corta(act['inicio'])}) fue cancelada.",
                f"/actividades/{actividad_id}",
            )


def listar_inscriptos(actividad_id: int) -> list[dict]:
    return db.query(
        "SELECT u.id, u.nombre, u.apellido, u.email, u.rol, c.nombre AS carrera, i.creado AS inscripto"
        " FROM inscripciones i"
        " JOIN usuarios u ON u.id = i.usuario_id"
        " LEFT JOIN carreras c ON c.id = u.carrera_id"
        " WHERE i.actividad_id = :id"
        " ORDER BY i.creado ASC, i.id ASC",
        id=actividad_id,
    )


def listar_inscripciones_de(usuario_id: int) -> list[dict]:
    """Actividades a las que está inscripto un estudiante, próximas primero."""
    filas = db.query(
        "SELECT a.*, (SELECT count(*) FROM inscripciones i2 WHERE i2.actividad_id = a.id) AS inscriptos"
        " FROM inscripciones i"
        " JOIN actividades a ON a.id = i.actividad_id"
        " WHERE i.usuario_id = :usuario"
        " ORDER BY COALESCE(a.fin, a.inicio) < :ahora, a.inicio ASC",
        usuario=usuario_id,
        ahora=ahora_local(),
    )
    for act in filas:
        act["inicio_formato"] = fecha_corta(act["inicio"])
    return filas
