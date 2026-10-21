from datetime import datetime

from davincihub import db
from davincihub.notificaciones import notificar
from davincihub.utiles import a_hora_local, ahora, ahora_local, fecha_corta

LIMITE_NOMBRE = 120
LIMITE_DESCRIPCION = 2000
LIMITE_UBICACION = 120
LIMITE_MOTIVO = 300


class ErrorActividad(ValueError):
    """Error base para operaciones sobre actividades."""


def _leer_fecha(valor: str, mensaje: str) -> datetime:
    try:
        return a_hora_local(datetime.fromisoformat(str(valor).strip()))
    except (ValueError, TypeError) as error:
        raise ErrorActividad(mensaje) from error


def _validar_fechas_actividad(inicio: str, fin: str | None = None) -> tuple[datetime, datetime | None]:
    """Parsea las fechas en hora de Buenos Aires y valida que el fin sea posterior al inicio."""
    if not inicio or not str(inicio).strip():
        raise ErrorActividad("La fecha y horario de inicio son obligatorios.")
    dt_ini = _leer_fecha(inicio, "Formato de fecha u hora de inicio inválido.")

    dt_fin = None
    if fin and str(fin).strip():
        dt_fin = _leer_fecha(fin, "Formato de fecha u hora de finalización inválido.")
        if dt_ini >= dt_fin:
            raise ErrorActividad("La hora de finalización debe ser posterior a la de inicio.")

    return dt_ini, dt_fin


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
    inicio: str,
    ubicacion: str,
    cupo_maximo: int,
    fin: str | None = None,
) -> int:
    """Crea una actividad propuesta por un estudiante en estado 'pendiente'."""
    nom = _texto(nombre, "el nombre", LIMITE_NOMBRE)
    desc = _texto(descripcion, "la descripción", LIMITE_DESCRIPCION)
    ubi = _texto(ubicacion, "la ubicación", LIMITE_UBICACION)

    try:
        cupo = int(cupo_maximo)
        if cupo <= 0:
            raise ValueError
    except (ValueError, TypeError) as error:
        raise ErrorActividad("El cupo máximo debe ser un número entero mayor a 0.") from error

    dt_ini, dt_fin = _validar_fechas_actividad(inicio, fin)

    if dt_ini < datetime.fromisoformat(ahora_local()):
        raise ErrorActividad("No se pueden crear actividades en fechas pasadas.")

    iso_ini = dt_ini.isoformat(timespec="seconds")
    iso_fin = dt_fin.isoformat(timespec="seconds") if dt_fin else None

    fila = db.query_one(
        "INSERT INTO actividades (creador_id, nombre, descripcion, inicio, fin, ubicacion, cupo_maximo, estado, creado)"
        " VALUES (:creador, :nombre, :descripcion, :inicio, :fin, :ubicacion, :cupo, 'pendiente', :creado)"
        " RETURNING id",
        creador=creador_id,
        nombre=nom,
        descripcion=desc,
        inicio=iso_ini,
        fin=iso_fin,
        ubicacion=ubi,
        cupo=cupo,
        creado=ahora(),
    )
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
        "       (SELECT count(*) FROM inscripciones i WHERE i.actividad_id = a.id) AS inscriptos"
        " FROM actividades a"
        " JOIN usuarios u ON u.id = a.creador_id"
        " WHERE a.id = :id",
        id=actividad_id,
    )
    if act:
        act["inicio_formato"] = fecha_corta(act["inicio"])
        act["fin_formato"] = fecha_corta(act["fin"]) if act["fin"] else None
    return act


def listar_actividades_publicas() -> list[dict]:
    """Lista las actividades aprobadas visibles para todos (RN-11)."""
    filas = db.query(
        "SELECT a.*, u.nombre AS creador_nombre, u.apellido AS creador_apellido,"
        "       (SELECT count(*) FROM inscripciones i WHERE i.actividad_id = a.id) AS inscriptos"
        " FROM actividades a"
        " JOIN usuarios u ON u.id = a.creador_id"
        " WHERE a.estado = 'aprobada' AND COALESCE(a.fin, a.inicio) >= :ahora"
        " ORDER BY a.inicio ASC",
        ahora=ahora_local(),
    )
    for act in filas:
        act["inicio_formato"] = fecha_corta(act["inicio"])
        act["fin_formato"] = fecha_corta(act["fin"]) if act["fin"] else None
    return filas


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
