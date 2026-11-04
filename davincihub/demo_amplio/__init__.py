"""Datos demo ampliados: más estudiantes, foro, objetos, chats y actividades sobre la base demo."""

import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from davincihub import db
from davincihub.demo_amplio import chat_largo, foro, moderacion, objetos, personas, social

DOMINIO = "davinci.edu.ar"
ORIGINALES = ("mica", "tomas", "lucia", "sofia", "bruno")
LEIDO_HASTA = "2026-10-23"


def _email(clave: str) -> str:
    return f"{clave}@{DOMINIO}"


def _insertar(sql: str, **valores) -> int:
    return db.query_one(sql + " RETURNING id", **valores)["id"]


def _avisar(usuario_id: int, tipo: str, cuerpo: str, enlace: str, creado: str):
    db.execute(
        "INSERT INTO notificaciones (usuario_id, tipo, cuerpo, enlace, leida, creado)"
        " VALUES (:usuario, :tipo, :cuerpo, :enlace, :leida, :creado)",
        usuario=usuario_id, tipo=tipo, cuerpo=cuerpo, enlace=enlace,
        leida=int(creado < LEIDO_HASTA), creado=creado,
    )


def _personas() -> tuple[dict, dict, dict]:
    carreras = {
        clave: db.query_one("SELECT id FROM carreras WHERE nombre = :nombre", nombre=nombre)["id"]
        for clave, nombre in personas.CARRERAS.items()
    }
    ids, nombres = {}, {}
    for clave in ORIGINALES:
        fila = db.query_one("SELECT id, nombre, apellido FROM usuarios WHERE email = :email", email=_email(clave))
        if fila:
            ids[clave] = fila["id"]
            nombres[clave] = f"{fila['nombre']} {fila['apellido']}"
    clave_hash = generate_password_hash("davinci123")
    for i, (clave, nombre, apellido, carrera, anio, comision, catedra, bloqueado) in enumerate(personas.ESTUDIANTES):
        ids[clave] = _insertar(
            "INSERT INTO usuarios (nombre, apellido, email, password_hash, rol, carrera_id, anio,"
            " comision, catedra, bloqueado, creado) VALUES (:nombre, :apellido, :email, :hash,"
            " 'estudiante', :carrera, :anio, :comision, :catedra, :bloqueado, :creado)",
            nombre=nombre, apellido=apellido, email=_email(clave), hash=clave_hash,
            carrera=carreras[carrera], anio=anio, comision=comision, catedra=int(catedra),
            bloqueado=int(bloqueado), creado=f"2026-09-{1 + i % 28:02d}T12:00:00+00:00",
        )
        nombres[clave] = f"{nombre} {apellido}"
        if bloqueado:
            admin = db.query_one("SELECT id FROM usuarios WHERE rol = 'admin' ORDER BY id")
            db.execute(
                "INSERT INTO bloqueos (usuario_id, admin_id, accion, motivo, creado)"
                " VALUES (:usuario, :admin, 'bloqueo', :motivo, '2026-10-12T16:00:00+00:00')",
                usuario=ids[clave], admin=admin["id"],
                motivo="Publicó equipos que no tenía y no respondió a los reportes de dos compañeros.",
            )
    return ids, nombres, carreras


def _conexiones(ids: dict, nombres: dict) -> int:
    for i, (solicitante, receptor, estado) in enumerate(personas.CONEXIONES):
        creado = f"2026-10-{1 + i % 24:02d}T{10 + i % 10:02d}:15:00+00:00"
        db.execute(
            "INSERT INTO conexiones (solicitante_id, receptor_id, estado, creado)"
            " VALUES (:solicitante, :receptor, :estado, :creado)",
            solicitante=ids[solicitante], receptor=ids[receptor], estado=estado, creado=creado,
        )
        if estado == "pendiente":
            _avisar(ids[receptor], "conexion", f"{nombres[solicitante]} quiere conectar con vos.",
                    f"/estudiantes/{ids[receptor]}/conexiones", creado)
        elif estado == "aceptada":
            _avisar(ids[solicitante], "conexion", f"{nombres[receptor]} aceptó tu solicitud de conexión.",
                    f"/estudiantes/{ids[receptor]}", creado)
    return len(personas.CONEXIONES)


def _foro(ids: dict, nombres: dict, carreras: dict) -> int:
    for pregunta in foro.PREGUNTAS:
        materia = db.query_one(
            "SELECT id FROM materias WHERE carrera_id = :carrera AND nombre = :nombre",
            carrera=carreras[pregunta["carrera"]], nombre=pregunta["materia"],
        )
        pregunta_id = _insertar(
            "INSERT INTO preguntas (autor_id, materia_id, titulo, cuerpo, creado)"
            " VALUES (:autor, :materia, :titulo, :cuerpo, :creado)",
            autor=ids[pregunta["autor"]], materia=materia["id"], titulo=pregunta["titulo"],
            cuerpo=pregunta["cuerpo"], creado=pregunta["creado"],
        )
        enlace = f"/foro/preguntas/{pregunta_id}"
        for respuesta in pregunta["respuestas"]:
            respuesta_id = _insertar(
                "INSERT INTO respuestas (pregunta_id, autor_id, cuerpo, aceptada, creado)"
                " VALUES (:pregunta, :autor, :cuerpo, :aceptada, :creado)",
                pregunta=pregunta_id, autor=ids[respuesta["autor"]], cuerpo=respuesta["cuerpo"],
                aceptada=int(respuesta.get("aceptada", False)), creado=respuesta["creado"],
            )
            if respuesta["autor"] != pregunta["autor"]:
                _avisar(ids[pregunta["autor"]], "foro", f"{nombres[respuesta['autor']]} respondió tu pregunta.",
                        enlace, respuesta["creado"])
            for votante in respuesta.get("utiles", []):
                db.execute(
                    "INSERT INTO valoraciones_respuestas (respuesta_id, usuario_id, valor, creado)"
                    " VALUES (:respuesta, :usuario, 1, :creado)",
                    respuesta=respuesta_id, usuario=ids[votante], creado=respuesta["creado"],
                )
            for hija in respuesta.get("hilo", []):
                db.execute(
                    "INSERT INTO respuestas (pregunta_id, autor_id, cuerpo, aceptada, creado, respuesta_padre_id)"
                    " VALUES (:pregunta, :autor, :cuerpo, 0, :creado, :padre)",
                    pregunta=pregunta_id, autor=ids[hija["autor"]], cuerpo=hija["cuerpo"],
                    creado=hija["creado"], padre=respuesta_id,
                )
                if hija["autor"] != respuesta["autor"]:
                    _avisar(ids[respuesta["autor"]], "foro", f"{nombres[hija['autor']]} respondió tu comentario.",
                            enlace, hija["creado"])
    return len(foro.PREGUNTAS)


def _objetos(ids: dict, carreras: dict) -> tuple[int, int]:
    from davincihub.objetos import busquedas

    for publicacion in objetos.PUBLICACIONES:
        carrera = publicacion.get("carrera")
        _insertar(
            "INSERT INTO publicaciones (autor_id, carrera_id, titulo, descripcion, categoria, estado_objeto,"
            " modalidad, precio, estado, creado) VALUES (:autor, :carrera, :titulo, :descripcion, :categoria,"
            " :estado_objeto, :modalidad, :precio, :estado, :creado)",
            autor=ids[publicacion["autor"]], carrera=carreras[carrera] if carrera else None,
            **{k: publicacion[k] for k in ("titulo", "descripcion", "categoria", "estado_objeto",
                                           "modalidad", "precio", "estado", "creado")},
        )
    for busqueda in objetos.BUSQUEDAS:
        solicitud_id = _insertar(
            "INSERT INTO solicitudes (autor_id, titulo, descripcion, categoria, modalidad, presupuesto_max,"
            " estado, creado) VALUES (:autor, :titulo, :descripcion, :categoria, :modalidad, :presupuesto_max,"
            " :estado, :creado)",
            autor=ids[busqueda["autor"]],
            **{k: busqueda[k] for k in ("titulo", "descripcion", "categoria", "modalidad",
                                        "presupuesto_max", "estado", "creado")},
        )
        busquedas.detectar_para_busqueda(solicitud_id)
    return len(objetos.PUBLICACIONES), len(objetos.BUSQUEDAS)


def _chats(ids: dict, nombres: dict) -> int:
    largos = {frozenset(c["entre"]) for c in chat_largo.CHATS_LARGOS}
    return sum(_insertar_chat(ids, nombres, chat) for chat in social.CHATS if frozenset(chat["entre"]) not in largos)


def _actividades(ids: dict) -> int:
    for actividad in social.ACTIVIDADES:
        espacio = db.query_one("SELECT id FROM espacios WHERE nombre = :nombre", nombre=actividad["espacio"])
        reserva_id = _insertar(
            "INSERT INTO reservas (espacio_id, usuario_id, inicio, fin, motivo, personas, estado, creado)"
            " VALUES (:espacio, :usuario, :inicio, :fin, :motivo, :personas, :estado, :creado)",
            espacio=espacio["id"], usuario=ids[actividad["creador"]], inicio=actividad["inicio"],
            fin=actividad["fin"], motivo=actividad["nombre"], personas=actividad["personas"],
            estado="cancelada" if actividad["estado"] in ("rechazada", "cancelada") else "confirmada",
            creado=actividad["creado"],
        )
        actividad_id = _insertar(
            "INSERT INTO actividades (creador_id, nombre, descripcion, inicio, fin, ubicacion, cupo_maximo,"
            " estado, motivo_rechazo, reserva_id, creado) VALUES (:creador, :nombre, :descripcion, :inicio,"
            " :fin, :ubicacion, :cupo, :estado, :motivo, :reserva, :creado)",
            creador=ids[actividad["creador"]], nombre=actividad["nombre"], descripcion=actividad["descripcion"],
            inicio=actividad["inicio"], fin=actividad["fin"], ubicacion=actividad["espacio"],
            cupo=actividad["cupo"], estado=actividad["estado"], motivo=actividad.get("motivo_rechazo"),
            reserva=reserva_id, creado=actividad["creado"],
        )
        for clave in actividad.get("inscriptos", []):
            db.execute(
                "INSERT INTO inscripciones (actividad_id, usuario_id, creado) VALUES (:actividad, :usuario, :creado)",
                actividad=actividad_id, usuario=ids[clave], creado=actividad["creado"],
            )
    return len(social.ACTIVIDADES)


def _ids_existentes() -> tuple[dict, dict]:
    ids, nombres = {}, {}
    claves = [e[0] for e in personas.ESTUDIANTES] + list(ORIGINALES)
    for clave in claves:
        fila = db.query_one("SELECT id, nombre, apellido FROM usuarios WHERE email = :email", email=_email(clave))
        if fila:
            ids[clave] = fila["id"]
            nombres[clave] = f"{fila['nombre']} {fila['apellido']}"
    return ids, nombres


def _chats_largos(ids: dict, nombres: dict) -> int:
    existentes = {frozenset(c["entre"]): c for c in social.CHATS}
    total = 0
    for chat in chat_largo.CHATS_LARGOS:
        uno, otro = (ids[c] for c in chat["entre"])
        db.execute(
            "DELETE FROM mensajes WHERE (emisor_id = :a AND receptor_id = :b) OR (emisor_id = :b AND receptor_id = :a)",
            a=uno, b=otro,
        )
        db.execute(
            "DELETE FROM notificaciones WHERE tipo = 'mensaje' AND enlace IN (:e1, :e2) AND usuario_id IN (:a, :b)",
            e1=f"/estudiantes/{uno}/chat", e2=f"/estudiantes/{otro}/chat", a=uno, b=otro,
        )
        previo = existentes.get(frozenset(chat["entre"]), {"mensajes": []})["mensajes"]
        mensajes = sorted({m[2]: m for m in [*previo, *chat["mensajes"]]}.values(), key=lambda m: m[2])
        total += _insertar_chat(ids, nombres, {"entre": chat["entre"], "mensajes": mensajes,
                                               "sin_leer": chat.get("sin_leer", 0)})
    return total


def _insertar_chat(ids: dict, nombres: dict, chat: dict) -> int:
    mensajes = chat["mensajes"]
    primero_sin_leer = len(mensajes) - chat.get("sin_leer", 0)
    for i, (emisor, cuerpo, creado) in enumerate(mensajes):
        receptor = next(p for p in chat["entre"] if p != emisor)
        db.execute(
            "INSERT INTO mensajes (emisor_id, receptor_id, cuerpo, leido, creado)"
            " VALUES (:emisor, :receptor, :cuerpo, :leido, :creado)",
            emisor=ids[emisor], receptor=ids[receptor], cuerpo=cuerpo,
            leido=int(i < primero_sin_leer), creado=creado,
        )
    if chat.get("sin_leer"):
        emisor, _, creado = mensajes[-1]
        receptor = next(p for p in chat["entre"] if p != emisor)
        db.execute(
            "INSERT INTO notificaciones (usuario_id, tipo, cuerpo, enlace, leida, creado)"
            " VALUES (:usuario, 'mensaje', :cuerpo, :enlace, 0, :creado)",
            usuario=ids[receptor], cuerpo=f"{nombres[emisor]} te escribió un mensaje.",
            enlace=f"/estudiantes/{ids[emisor]}/chat", creado=creado,
        )
    return len(mensajes)


def _objeto_reportado(ids: dict, tipo: str, criterio: tuple[str, str]) -> int:
    campo, valor = criterio
    if campo == "clave":
        return ids[valor]
    tabla, columna = {
        "publicacion": ("publicaciones", "titulo"), "pregunta": ("preguntas", "titulo"),
        "respuesta": ("respuestas", "cuerpo"), "actividad": ("actividades", "nombre"),
    }[tipo]
    patron = valor if campo in ("titulo", "nombre", "cuerpo") else valor + "%"
    operador = "=" if campo in ("titulo", "nombre", "cuerpo") else "LIKE"
    return db.query_one(f"SELECT id FROM {tabla} WHERE {columna} {operador} :v ORDER BY id LIMIT 1", v=patron)["id"]


def _reportes(ids: dict) -> int:
    admin = db.query_one("SELECT id FROM usuarios WHERE rol = 'admin' ORDER BY id")["id"]
    tablas = {"publicacion": "publicaciones", "pregunta": "preguntas", "respuesta": "respuestas", "actividad": "actividades"}
    for autor, tipo, criterio, motivo, accion, resolucion, creado in moderacion.REPORTES:
        objeto = _objeto_reportado(ids, tipo, criterio)
        db.execute(
            "INSERT INTO reportes (autor_id, tipo_objeto, objeto_id, motivo, estado, accion, resolucion,"
            " resuelto_por, resuelto, creado) VALUES (:autor, :tipo, :objeto, :motivo, :estado, :accion,"
            " :resolucion, :admin, :resuelto, :creado)",
            autor=ids[autor], tipo=tipo, objeto=objeto, motivo=motivo,
            estado="resuelto" if accion else "pendiente", accion=accion, resolucion=resolucion,
            admin=admin if accion else None, resuelto=creado if accion else None, creado=creado,
        )
        if accion == "ocultar":
            db.execute(f"UPDATE {tablas[tipo]} SET oculto = 1 WHERE id = :id", id=objeto)
        if accion:
            _avisar(ids[autor], "reportes", "Revisamos tu reporte." if accion == "descartar"
                    else "Revisamos tu reporte: el contenido ya no es visible para la comunidad.", None, creado)
    return len(moderacion.REPORTES)


def _extra_cargado() -> bool:
    return db.query_one("SELECT 1 AS hay FROM reportes WHERE motivo = :m AND creado = :c",
                        m=moderacion.REPORTES[0][3], c=moderacion.REPORTES[0][6]) is not None


def cargar() -> dict:
    if not db.query_one("SELECT id FROM usuarios WHERE email = :email", email=_email("mica")):
        raise click.ClickException("Primero cargá la base demo: flask --app davincihub.app init-db --demo")
    base_cargada = db.query_one("SELECT id FROM usuarios WHERE email = :email",
                                email=_email(personas.ESTUDIANTES[0][0])) is not None
    if base_cargada and _extra_cargado():
        raise click.ClickException("Los datos ampliados ya están cargados en esta base.")
    resumen = {}
    with db.transaccion():
        if base_cargada:
            ids, nombres = _ids_existentes()
        else:
            ids, nombres, carreras = _personas()
            resumen = {
                "estudiantes": len(personas.ESTUDIANTES),
                "conexiones": _conexiones(ids, nombres),
                "preguntas": _foro(ids, nombres, carreras),
            }
            resumen["publicaciones"], resumen["busquedas"] = _objetos(ids, carreras)
            resumen["mensajes"] = _chats(ids, nombres)
            resumen["actividades"] = _actividades(ids)
        resumen["mensajes en chats largos"] = _chats_largos(ids, nombres)
        resumen["reportes"] = _reportes(ids)
    return resumen


@click.command("seed-amplio")
@with_appcontext
def comando_seed_amplio():
    """Suma estudiantes, foro, objetos, chats y actividades a la base demo sin borrar nada."""
    resumen = cargar()
    click.echo("Datos ampliados cargados: " + ", ".join(f"{v} {k}" for k, v in resumen.items()) + ".")
