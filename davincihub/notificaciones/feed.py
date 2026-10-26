"""Agrupa los avisos de la bandeja y les suma contexto: quién, sobre qué y una vista previa."""

import re
from datetime import datetime, timedelta

from davincihub import db
from davincihub.utiles import ZONA_LOCAL

ICONOS = {"foro": "foro", "objetos": "objetos", "mensaje": "mensaje", "conexion": "conexion",
          "actividades": "actividades", "reservas": "reservas"}


def _dia(iso: str) -> datetime:
    momento = datetime.fromisoformat(iso)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=ZONA_LOCAL)
    return momento.astimezone(ZONA_LOCAL)


def _seccion(iso: str, hoy) -> str:
    dias = (hoy - _dia(iso).date()).days
    if dias <= 0:
        return "Hoy"
    if dias == 1:
        return "Ayer"
    return "Esta semana" if dias < 7 else "Anteriores"


def _persona(usuario_id: int) -> dict | None:
    return db.query_one(
        "SELECT u.id, u.nombre, u.apellido,"
        " EXISTS (SELECT 1 FROM fotos_perfil f WHERE f.usuario_id = u.id) AS tiene_foto"
        " FROM usuarios u WHERE u.id = :id",
        id=usuario_id,
    )


def _nombre_en(cuerpo: str, verbo: str) -> str | None:
    partes = cuerpo.split(f" {verbo}", 1)
    return partes[0] if len(partes) == 2 else None


def _numero(patron: str, enlace: str | None) -> int | None:
    coincidencia = re.fullmatch(patron, enlace or "")
    return int(coincidencia.group(1)) if coincidencia else None


def _completar(grupo: dict, yo: int) -> None:
    tipo, enlace, avisos = grupo["tipo"], grupo["enlace"], grupo["avisos"]
    cantidad = len(avisos)
    grupo["titulo"], grupo["detalle"] = avisos[0]["cuerpo"], None

    if tipo == "mensaje" and (otro := _numero(r"/estudiantes/(\d+)/chat", enlace)):
        persona = _persona(otro)
        if persona:
            grupo["personas"] = [persona]
            grupo["titulo"] = f"{persona['nombre']} {persona['apellido']} te escribió"
            ultimo = db.query_one(
                "SELECT cuerpo FROM mensajes WHERE emisor_id = :otro AND receptor_id = :yo"
                " ORDER BY creado DESC, id DESC LIMIT 1",
                otro=otro, yo=yo,
            )
            grupo["detalle"] = ultimo["cuerpo"] if ultimo else None
    elif tipo == "conexion" and (otro := _numero(r"/estudiantes/(\d+)", enlace)):
        persona = _persona(otro)
        if persona:
            grupo["personas"] = [persona]
            grupo["titulo"] = f"{persona['nombre']} {persona['apellido']} aceptó tu solicitud"
            grupo["detalle"] = "Ya forman parte de tu red: pueden escribirse por chat."
    elif tipo == "conexion":
        nombre = _nombre_en(avisos[0]["cuerpo"], "quiere conectar")
        if nombre:
            grupo["iniciales"] = [nombre]
            grupo["titulo"] = f"{nombre} quiere conectar con vos"
    elif tipo == "foro" and (pregunta_id := _numero(r"/foro/preguntas/(\d+)", enlace)):
        pregunta = db.query_one("SELECT titulo FROM preguntas WHERE id = :id", id=pregunta_id)
        nombres = []
        for aviso in avisos:
            nombre = _nombre_en(aviso["cuerpo"], "respondió")
            if nombre and nombre not in nombres:
                nombres.append(nombre)
        grupo["iniciales"] = nombres[:2]
        if cantidad == 1 and nombres:
            accion = "tu comentario" if "comentario" in avisos[0]["cuerpo"] else "tu pregunta"
            grupo["titulo"] = f"{nombres[0]} respondió {accion}"
        else:
            grupo["titulo"] = f"{cantidad} respuestas nuevas"
        grupo["detalle"] = f"«{pregunta['titulo']}»" if pregunta else None
    elif tipo == "objetos" and (solicitud_id := _numero(r"/objetos/busquedas/(\d+)", enlace)):
        solicitud = db.query_one("SELECT titulo FROM solicitudes WHERE id = :id", id=solicitud_id)
        grupo["titulo"] = "Una posible coincidencia" if cantidad == 1 else f"{cantidad} posibles coincidencias"
        grupo["detalle"] = f"Para tu búsqueda «{solicitud['titulo']}»" if solicitud else None
        grupo["objetos"] = db.query(
            "SELECT p.id, p.titulo, p.categoria, p.modalidad, p.precio FROM coincidencias c"
            " JOIN publicaciones p ON p.id = c.publicacion_id"
            " WHERE c.solicitud_id = :solicitud AND p.estado = 'activa'"
            " ORDER BY c.creado DESC, c.id DESC LIMIT 3",
            solicitud=solicitud_id,
        )


def agrupar(avisos: list[dict], yo: int) -> list[tuple[str, list[dict]]]:
    hoy = datetime.now(ZONA_LOCAL).date()
    secciones: dict[str, list[dict]] = {}
    indice: dict[tuple, dict] = {}
    for aviso in avisos:
        seccion = _seccion(aviso["creado"], hoy)
        clave = (seccion, aviso["tipo"], aviso["enlace"]) if aviso["enlace"] else (seccion, aviso["id"])
        grupo = indice.get(clave)
        if grupo is None:
            grupo = indice[clave] = {
                "id": aviso["id"], "tipo": aviso["tipo"], "enlace": aviso["enlace"], "creado": aviso["creado"],
                "icono": ICONOS.get(aviso["tipo"], "general"), "avisos": [], "personas": [], "iniciales": [],
                "objetos": [], "sin_leer": 0,
            }
            secciones.setdefault(seccion, []).append(grupo)
        grupo["avisos"].append(aviso)
        grupo["sin_leer"] += 0 if aviso["leida"] else 1
    for grupo in indice.values():
        _completar(grupo, yo)
    orden = ["Hoy", "Ayer", "Esta semana", "Anteriores"]
    return [(nombre, secciones[nombre]) for nombre in orden if nombre in secciones]


def solicitudes_pendientes(yo: int) -> list[dict]:
    return db.query(
        "SELECT u.id, u.nombre, u.apellido, u.anio, c.nombre AS carrera,"
        " EXISTS (SELECT 1 FROM fotos_perfil f WHERE f.usuario_id = u.id) AS tiene_foto"
        " FROM conexiones x JOIN usuarios u ON u.id = x.solicitante_id"
        " LEFT JOIN carreras c ON c.id = u.carrera_id"
        " WHERE x.receptor_id = :yo AND x.estado = 'pendiente' AND u.bloqueado = 0"
        " ORDER BY x.creado DESC LIMIT 6",
        yo=yo,
    )


def tiempo_relativo(iso: str) -> str:
    momento = _dia(iso)
    ahora = datetime.now(ZONA_LOCAL)
    diferencia = ahora - momento
    if diferencia < timedelta(minutes=1):
        return "ahora"
    if diferencia < timedelta(hours=1):
        return f"hace {int(diferencia.total_seconds() // 60)} min"
    if diferencia < timedelta(days=1) and momento.date() == ahora.date():
        return f"hace {int(diferencia.total_seconds() // 3600)} h"
    return momento.strftime("%d/%m %H:%M")
