"""Capa de datos del módulo de actividades.

Reglas de negocio implementadas:
- RN-12 / CA-08: el cupo máximo nunca se supera, incluso con inscripciones simultáneas
  (se usa SELECT … FOR UPDATE / EXCLUSIVE en SQLite para serializar las escrituras).
- Un estudiante no puede inscribirse dos veces a la misma actividad.
- Solo se puede inscribir en actividades con estado 'aprobada' y fecha de inicio futura.
- El creador de la actividad no puede inscribirse en ella.
- Las notificaciones se emiten al creador (nueva inscripción) y a todos los inscriptos
  (cambio de estado o cancelación de la actividad).
"""

from __future__ import annotations

from datetime import UTC, datetime

from davincihub import db

# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------


class ErrorActividad(Exception):
    """Error de validación o regla de negocio en el módulo de actividades."""


class ErrorInscripcion(Exception):
    """Error de validación o regla de negocio al inscribirse en una actividad."""


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

_ESTADOS_VALIDOS = ("pendiente", "aprobada", "rechazada", "cancelada")


def _ahora_iso() -> str:
    return datetime.now(UTC).isoformat()


def _actividad_o_error(actividad_id: int) -> dict:
    actividad = db.query_one("SELECT * FROM actividades WHERE id = :id", id=actividad_id)
    if not actividad:
        raise ErrorActividad(f"No existe la actividad con id {actividad_id}.")
    return actividad


# ---------------------------------------------------------------------------
# Consultas de actividades
# ---------------------------------------------------------------------------


def listar_actividades(estado: str | None = None) -> list[dict]:
    """Lista actividades con cupo disponible calculado.

    Si *estado* es None devuelve todas; en caso contrario filtra por ese estado.
    """
    filtro = "AND a.estado = :estado" if estado else ""
    filas = db.query(
        f"""
        SELECT
            a.*,
            u.nombre  AS creador_nombre,
            u.apellido AS creador_apellido,
            COUNT(i.id) AS inscriptos,
            (a.cupo_maximo - COUNT(i.id)) AS cupo_disponible
        FROM actividades a
        JOIN usuarios u ON u.id = a.creador_id
        LEFT JOIN inscripciones i ON i.actividad_id = a.id
        {filtro}
        GROUP BY a.id
        ORDER BY a.inicio ASC
        """,
        **( {"estado": estado} if estado else {} ),
    )
    return filas


def listar_actividades_publicas() -> list[dict]:
    """Actividades aprobadas, ordenadas por fecha de inicio."""
    return listar_actividades(estado="aprobada")


def listar_actividades_admin() -> list[dict]:
    """Todas las actividades para la vista de administración."""
    return listar_actividades()


def listar_actividades_creadas_por(usuario_id: int) -> list[dict]:
    """Actividades creadas por un usuario, con cupo calculado."""
    filas = db.query(
        """
        SELECT
            a.*,
            COUNT(i.id) AS inscriptos,
            (a.cupo_maximo - COUNT(i.id)) AS cupo_disponible
        FROM actividades a
        LEFT JOIN inscripciones i ON i.actividad_id = a.id
        WHERE a.creador_id = :uid
        GROUP BY a.id
        ORDER BY a.inicio DESC
        """,
        uid=usuario_id,
    )
    return filas


def listar_inscripciones_de(usuario_id: int) -> list[dict]:
    """Actividades a las que está inscripto un estudiante."""
    return db.query(
        """
        SELECT
            a.*,
            u.nombre  AS creador_nombre,
            u.apellido AS creador_apellido,
            COUNT(i2.id) AS inscriptos,
            (a.cupo_maximo - COUNT(i2.id)) AS cupo_disponible,
            insc.creado AS fecha_inscripcion
        FROM inscripciones insc
        JOIN actividades a ON a.id = insc.actividad_id
        JOIN usuarios u ON u.id = a.creador_id
        LEFT JOIN inscripciones i2 ON i2.actividad_id = a.id
        WHERE insc.usuario_id = :uid
        GROUP BY a.id
        ORDER BY a.inicio ASC
        """,
        uid=usuario_id,
    )


def obtener_actividad(actividad_id: int) -> dict | None:
    """Actividad con cupo calculado e inscriptos."""
    fila = db.query_one(
        """
        SELECT
            a.*,
            u.nombre  AS creador_nombre,
            u.apellido AS creador_apellido,
            COUNT(i.id) AS inscriptos,
            (a.cupo_maximo - COUNT(i.id)) AS cupo_disponible
        FROM actividades a
        JOIN usuarios u ON u.id = a.creador_id
        LEFT JOIN inscripciones i ON i.actividad_id = a.id
        WHERE a.id = :id
        GROUP BY a.id
        """,
        id=actividad_id,
    )
    return fila


def listar_inscriptos(actividad_id: int) -> list[dict]:
    """Lista de usuarios inscriptos en una actividad, ordenados por fecha de inscripción."""
    return db.query(
        """
        SELECT
            u.id, u.nombre, u.apellido, u.email,
            c.nombre AS carrera_nombre,
            i.creado AS fecha_inscripcion
        FROM inscripciones i
        JOIN usuarios u ON u.id = i.usuario_id
        LEFT JOIN carreras c ON c.id = u.carrera_id
        WHERE i.actividad_id = :actividad_id
        ORDER BY i.creado ASC
        """,
        actividad_id=actividad_id,
    )


def esta_inscripto(actividad_id: int, usuario_id: int) -> bool:
    """Indica si el usuario ya está inscripto en la actividad."""
    fila = db.query_one(
        "SELECT id FROM inscripciones WHERE actividad_id = :a AND usuario_id = :u",
        a=actividad_id,
        u=usuario_id,
    )
    return fila is not None


# ---------------------------------------------------------------------------
# Inscripción / baja
# ---------------------------------------------------------------------------


def inscribir(actividad_id: int, usuario_id: int) -> None:
    """Inscribe al usuario en la actividad.

    Serializa el acceso con una transacción exclusiva para evitar que dos
    inscripciones simultáneas al último lugar superen el cupo (RN-12 / CA-08).

    Raises:
        ErrorInscripcion: si se viola alguna regla de negocio.
    """
    with db.transaccion():
        # Bloqueo de fila para serializar escrituras concurrentes
        if not db.bloquear_fila("actividades", actividad_id):
            raise ErrorInscripcion("La actividad no existe.")

        actividad = db.query_one("SELECT * FROM actividades WHERE id = :id", id=actividad_id)

        # --- Validaciones de reglas de negocio ---
        if actividad["estado"] != "aprobada":
            raise ErrorInscripcion("Solo podés inscribirte en actividades aprobadas.")

        if actividad["creador_id"] == usuario_id:
            raise ErrorInscripcion("El creador no puede inscribirse en su propia actividad.")

        if esta_inscripto(actividad_id, usuario_id):
            raise ErrorInscripcion("Ya estás inscripto en esta actividad.")

        inicio = datetime.fromisoformat(actividad["inicio"])
        if inicio.tzinfo is None:
            inicio = inicio.replace(tzinfo=UTC)
        if inicio <= datetime.now(UTC):
            raise ErrorInscripcion("No podés inscribirte en una actividad que ya comenzó.")

        # Verificar cupo en este mismo momento (ya dentro de la transacción)
        inscriptos = db.query_one(
            "SELECT COUNT(*) AS total FROM inscripciones WHERE actividad_id = :id",
            id=actividad_id,
        )["total"]
        if inscriptos >= actividad["cupo_maximo"]:
            raise ErrorInscripcion("La actividad ya no tiene lugares disponibles.")

        db.execute(
            "INSERT INTO inscripciones (actividad_id, usuario_id, creado)"
            " VALUES (:a, :u, :creado)",
            a=actividad_id,
            u=usuario_id,
            creado=_ahora_iso(),
        )
        _notificar_creador_nueva_inscripcion(actividad, usuario_id)


def dar_de_baja(actividad_id: int, usuario_id: int) -> None:
    """Da de baja al usuario de la actividad.

    Raises:
        ErrorInscripcion: si el usuario no estaba inscripto o la actividad ya pasó.
    """
    actividad = db.query_one("SELECT * FROM actividades WHERE id = :id", id=actividad_id)
    if not actividad:
        raise ErrorInscripcion("La actividad no existe.")

    if not esta_inscripto(actividad_id, usuario_id):
        raise ErrorInscripcion("No estás inscripto en esta actividad.")

    inicio = datetime.fromisoformat(actividad["inicio"])
    if inicio.tzinfo is None:
        inicio = inicio.replace(tzinfo=UTC)
    if inicio <= datetime.now(UTC):
        raise ErrorInscripcion("No podés darte de baja de una actividad que ya comenzó.")

    db.execute(
        "DELETE FROM inscripciones WHERE actividad_id = :a AND usuario_id = :u",
        a=actividad_id,
        u=usuario_id,
    )


# ---------------------------------------------------------------------------
# Gestión de actividades (admin / creador)
# ---------------------------------------------------------------------------


def crear_actividad(
    creador_id: int,
    nombre: str,
    descripcion: str,
    inicio: str,
    fin: str | None,
    ubicacion: str,
    cupo_maximo: int,
) -> int:
    """Crea una actividad en estado 'pendiente' y devuelve su id."""
    nombre = nombre.strip()
    descripcion = descripcion.strip()
    ubicacion = ubicacion.strip()

    if not nombre:
        raise ErrorActividad("El nombre es obligatorio.")
    if not descripcion:
        raise ErrorActividad("La descripción es obligatoria.")
    if not ubicacion:
        raise ErrorActividad("La ubicación es obligatoria.")
    if not inicio:
        raise ErrorActividad("La fecha de inicio es obligatoria.")
    try:
        cupo_maximo = int(cupo_maximo)
        if cupo_maximo <= 0:
            raise ValueError
    except (TypeError, ValueError):
        raise ErrorActividad("El cupo máximo debe ser un número mayor a 0.")

    fila = db.query_one(
        """
        INSERT INTO actividades
            (creador_id, nombre, descripcion, inicio, fin, ubicacion, cupo_maximo, estado, creado)
        VALUES (:creador_id, :nombre, :descripcion, :inicio, :fin, :ubicacion, :cupo_maximo, 'pendiente', :creado)
        RETURNING id
        """,
        creador_id=creador_id,
        nombre=nombre,
        descripcion=descripcion,
        inicio=inicio,
        fin=fin or None,
        ubicacion=ubicacion,
        cupo_maximo=cupo_maximo,
        creado=_ahora_iso(),
    )
    return fila["id"]


def cambiar_estado(actividad_id: int, nuevo_estado: str, motivo: str | None = None) -> None:
    """Cambia el estado de una actividad (admin).

    Al cancelar, notifica a todos los inscriptos.
    """
    if nuevo_estado not in _ESTADOS_VALIDOS:
        raise ErrorActividad(f"Estado inválido: {nuevo_estado!r}.")

    with db.transaccion():
        if not db.bloquear_fila("actividades", actividad_id):
            raise ErrorActividad(f"No existe la actividad con id {actividad_id}.")
        _actividad_o_error(actividad_id)

        db.execute(
            "UPDATE actividades SET estado = :estado, motivo_rechazo = :motivo WHERE id = :id",
            estado=nuevo_estado,
            motivo=motivo or None,
            id=actividad_id,
        )

        if nuevo_estado in ("cancelada", "rechazada"):
            _notificar_inscriptos_cambio(actividad_id, nuevo_estado)


# ---------------------------------------------------------------------------
# Notificaciones internas
# ---------------------------------------------------------------------------


def _notificar_creador_nueva_inscripcion(actividad: dict, usuario_id: int) -> None:
    usuario = db.query_one("SELECT nombre, apellido FROM usuarios WHERE id = :id", id=usuario_id)
    if not usuario:
        return
    nombre = f"{usuario['nombre']} {usuario['apellido']}"
    db.execute(
        "INSERT INTO notificaciones (usuario_id, tipo, cuerpo, enlace, creado)"
        " VALUES (:uid, 'actividades', :cuerpo, :enlace, :creado)",
        uid=actividad["creador_id"],
        cuerpo=f"{nombre} se inscribió en tu actividad «{actividad['nombre']}».",
        enlace=f"/actividades/{actividad['id']}/inscriptos",
        creado=_ahora_iso(),
    )


def _notificar_inscriptos_cambio(actividad_id: int, nuevo_estado: str) -> None:
    actividad = db.query_one("SELECT nombre FROM actividades WHERE id = :id", id=actividad_id)
    if not actividad:
        return
    verbo = "cancelada" if nuevo_estado == "cancelada" else "rechazada"
    inscriptos = db.query(
        "SELECT usuario_id FROM inscripciones WHERE actividad_id = :id", id=actividad_id
    )
    for insc in inscriptos:
        db.execute(
            "INSERT INTO notificaciones (usuario_id, tipo, cuerpo, enlace, creado)"
            " VALUES (:uid, 'actividades', :cuerpo, :enlace, :creado)",
            uid=insc["usuario_id"],
            cuerpo=f"La actividad «{actividad['nombre']}» fue {verbo}.",
            enlace=f"/actividades/{actividad_id}",
            creado=_ahora_iso(),
        )
