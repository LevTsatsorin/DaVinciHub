"""Ejemplos aditivos: operaciones, opiniones, búsquedas y reservas para todos los estudiantes demo."""

from datetime import date, datetime, time, timedelta

import click
from flask.cli import with_appcontext

from davincihub import db
from davincihub.notificaciones import notificar
from davincihub.objetos import busquedas
from davincihub.reservas import datos as reservas
from davincihub.utiles import ZONA_LOCAL, hoy_local

ESTUDIANTES = (
    "mica", "tomas", "lucia", "sofia", "valen", "joaco", "cami", "nacho", "flor", "santi", "agus", "rocio",
    "thiago", "mai", "lauti", "pili", "fede", "delfi", "tomi", "abril", "mateo", "juli", "benja", "martu",
    "franco", "ludmi", "nico", "euge", "gonza", "ivan", "sol", "bauti", "cande", "mariangeles", "jo", "kevin",
)
# título, categoría, modalidad, precio, descripción
MATERIALES = (
    ("Wacom Intuos S con lápiz", "dibujo_diseno", "venta", 68000, "Poco uso, con puntas de repuesto y cable original."),
    ("Atril de mesa para bocetos", "dibujo_diseno", "prestamo", None, "Regulable en altura, ideal para las entregas de dibujo."),
    ("Marcadores Copic Ciao x12", "dibujo_diseno", "intercambio", None, "Tonos de piel y grises. Los cambio por acuarelas."),
    ("Kindle con manuales de UX", "libros_apuntes", "prestamo", None, "Cargado con material de la cátedra de interfaces."),
    ("Don't Make Me Think, edición en inglés", "libros_apuntes", "venta", 18000, "Algunas páginas subrayadas en lápiz."),
    ("Apuntes completos de Semiótica", "libros_apuntes", "intercambio", None, "Carpeta entera de la cursada. Los cambio por los de Guion."),
    ("Blackmagic Pocket 4K (cuerpo)", "foto_video", "prestamo", None, "Con dos baterías. Para rodajes de la escuela."),
    ("Lente Sigma 18-35 f/1.8", "foto_video", "venta", 410000, "Montura Canon, sin hongos ni rayones."),
    ("Filtro ND variable de 77 mm", "foto_video", "intercambio", None, "Lo cambio por un adaptador o un filtro polarizador."),
    ("Zoom H1n con paravientos", "audio_iluminacion", "prestamo", None, "Grabador de mano con tarjeta de 16 GB."),
    ("Micrófono Rode VideoMic Go", "audio_iluminacion", "venta", 75000, "Funciona perfecto, con su shock mount."),
    ("Panel LED bicolor Godox", "audio_iluminacion", "intercambio", None, "Con batería. Lo cambio por un trípode de video."),
    ("SSD externo Samsung T7 1 TB", "computacion", "venta", 115000, "Salud al 98%, lo cambié por uno más grande."),
    ("Teclado mecánico Redragon", "computacion", "intercambio", None, "Switches rojos. Lo cambio por un mouse vertical."),
    ("Notebook para render de emergencia", "computacion", "prestamo", None, "Ryzen 7 con 32 GB, para entregas puntuales."),
    ("Regla T y escuadras de dibujo", "utiles", "venta", 9000, "Todo el set de Representación Gráfica."),
    ("Tablero A2 con paralelo", "utiles", "prestamo", None, "Liviano, viene con funda para transportarlo."),
    ("Cortante y base de corte A3", "utiles", "intercambio", None, "La base está casi nueva. Lo cambio por papel."),
    ("Monitor Dell de 24 pulgadas", "computacion", "venta", 145000, "Panel IPS calibrado, con cable HDMI."),
    ("Trípode Manfrotto Befree", "foto_video", "prestamo", None, "Compacto, con cabezal de bola."),
    ("Set de acuarelas Winsor & Newton", "dibujo_diseno", "intercambio", None, "24 pastillas, faltan muy pocas."),
    ("Interfaz Focusrite Scarlett Solo", "audio_iluminacion", "venta", 130000, "Con cable USB, tercera generación."),
    ("Libro Story de Robert McKee", "libros_apuntes", "prestamo", None, "El clásico de guion, en muy buen estado."),
    ("Gamepad para testear prototipos", "computacion", "intercambio", None, "Compatible con PC. Lo cambio por un hub USB."),
    ("Cámara Canon T7i con kit", "foto_video", "venta", 480000, "Pocos disparos, con bolso y dos baterías."),
    ("Softbox plegable 60x60", "audio_iluminacion", "prestamo", None, "Para fotografía de producto, entra en una mochila."),
    ("Libro Thinking with Type", "libros_apuntes", "intercambio", None, "Lo cambio por otro de tipografía o de color."),
    ("Mouse vertical Logitech Lift", "computacion", "venta", 42000, "Inalámbrico, ideal para muchas horas de edición."),
    ("Maniquí articulado de dibujo", "dibujo_diseno", "prestamo", None, "Para practicar poses en Ilustración."),
    ("Fondo de croma de 3 x 2 m", "foto_video", "intercambio", None, "Con soporte. Lo cambio por luces."),
    ("Pack de pinceles Pentel", "dibujo_diseno", "venta", 15000, "Con depósito de agua, casi sin usar."),
    ("Auriculares Audio-Technica M40x", "audio_iluminacion", "prestamo", None, "Para mezclar sin molestar en el taller."),
    ("Calibrador de color Spyder", "computacion", "intercambio", None, "Lo cambio por una tableta chica."),
    ("Apuntes de Historia del Cine", "libros_apuntes", "venta", 6000, "Resúmenes por unidad, listos para el final."),
    ("Mochila Lowepro para cámara", "utiles", "prestamo", None, "Entran cuerpo, tres lentes y notebook."),
    ("Agenda y planificador de rodaje", "utiles", "intercambio", None, "Sin usar, lo cambio por cuadernos."),
    ("Tableta XP-Pen Artist 12", "dibujo_diseno", "venta", 210000, "Con pantalla, pocas marcas en el vidrio."),
    ("Cable XLR de 5 metros", "audio_iluminacion", "prestamo", None, "Dos unidades, probadas y funcionando."),
    ("Lámpara de mesa para maquetas", "utiles", "venta", 12000, "Luz cálida y fría, con brazo flexible."),
    ("Hub USB-C de 7 puertos", "computacion", "intercambio", None, "Lo cambio por un lector de tarjetas."),
    ("Estabilizador Zhiyun Smooth", "foto_video", "prestamo", None, "Para celulares, con estuche y cargador."),
    ("Libro El ojo del fotógrafo", "libros_apuntes", "venta", 14000, "Edición en castellano, como nuevo."),
    ("Papel Canson A3 x 50 hojas", "dibujo_diseno", "intercambio", None, "Me sobró de la cursada. Lo cambio por lápices."),
    ("Reflector plegable 5 en 1", "foto_video", "venta", 20000, "Con bolso, sin marcas."),
    ("Consola Nintendo Switch para game testing", "computacion", "prestamo", None, "Solo para pruebas de la materia, con joycons."),
    ("Set de reglas curvas", "utiles", "intercambio", None, "Lo cambio por marcadores finos."),
    ("Micrófono corbatero Boya", "audio_iluminacion", "venta", 16000, "Con adaptador para celular."),
    ("Caja de luz LED A4", "dibujo_diseno", "prestamo", None, "Para calcar en Animación 2D."),
)
ESTADOS_PRESTAMO = ("devuelto", "pendiente", "en_prestamo", "devuelto", "aceptado", "vencido", "cancelado")
ESTADOS_ACUERDO = ("completado", "propuesto", "completado", "aceptado", "cancelado")
VENTA = {"propuesto": "propuesta", "aceptado": "aceptada", "completado": "completada", "cancelado": "cancelada"}
PUNTAJES = (5, 4, 5, 3, 5, 5, 4, 2, 5, 4)
COMENTARIOS = {
    5: ("Todo impecable, súper puntual.", "Un golazo, lo recomiendo.", "Excelente onda y el material como lo describió."),
    4: ("Muy bien, tardamos un poco en coordinar.", "Buena experiencia, volvería a operar."),
    3: ("Cumplió, aunque costó encontrar un horario.",),
    2: ("Llegó bastante tarde y hubo que reprogramar dos veces.",),
}
BUSQUEDAS = (
    ("Busco tableta gráfica chica", "dibujo_diseno", "venta", 60000),
    ("Necesito cámara para un corto", "foto_video", "prestamo", None),
    ("Apuntes de primer año", "libros_apuntes", "cualquiera", None),
    ("Micrófono para entrevistas", "audio_iluminacion", "prestamo", None),
    ("Disco externo para proyectos", "computacion", "venta", 90000),
    ("Materiales de maqueta", "utiles", "intercambio", None),
)
ESPACIOS_RESERVA = ("Aula de Informática 1", "Aula de Informática 2", "Aula de Arte y Diseño")
MOTIVOS = ("Práctica para la entrega final", "Práctica grupal de la materia", "Práctica de render y edición")


def _momento(dia, hora=10):
    return datetime.combine(dia, time(hora), tzinfo=ZONA_LOCAL).isoformat(timespec="seconds")


def _movimiento_prestamo(prestamo, anterior, nuevo, actor, detalle, creado):
    db.execute(
        "INSERT INTO prestamos_movimientos (prestamo_id, estado_anterior, estado_nuevo, actor_id, detalle, creado)"
        " VALUES (:p, :a, :n, :actor, :d, :c)", p=prestamo, a=anterior, n=nuevo, actor=actor, d=detalle, c=creado,
    )


def _prestamo(publicacion, dueno, quien, estado, hoy):
    finalizado = estado in ("devuelto", "vencido")
    inicio = hoy - timedelta(days=12 if finalizado else 3 if estado == "en_prestamo" else -2)
    fin = hoy - timedelta(days=3) if finalizado else hoy + timedelta(days=7)
    creado = _momento(inicio - timedelta(days=2))
    entregado = _momento(inicio) if estado in ("en_prestamo", "vencido", "devuelto") else None
    devuelto = _momento(fin) if estado == "devuelto" else None
    condiciones = "" if estado in ("pendiente", "cancelado") else "Retiramos en la escuela y se devuelve en el mismo estado."
    motivo = "Al final conseguí otro para esa fecha." if estado == "cancelado" else ""
    pid = db.query_one(
        "INSERT INTO prestamos (publicacion_id, solicitante_id, estado, fecha_entrega, fecha_devolucion, condiciones,"
        " mensaje, motivo_cierre, entregado, devuelto, creado) VALUES (:p, :q, :e, :i, :f, :cond, :m, :motivo,"
        " :ent, :dev, :c) RETURNING id",
        p=publicacion, q=quien, e=estado, i=inicio.isoformat(), f=fin.isoformat(), cond=condiciones,
        m="Lo necesito para una entrega. Lo cuido como propio.", motivo=motivo, ent=entregado, dev=devuelto, c=creado,
    )["id"]
    _movimiento_prestamo(pid, None, "pendiente", quien, "Solicitud enviada.", creado)
    if estado == "cancelado":
        _movimiento_prestamo(pid, "pendiente", "cancelado", quien, motivo, _momento(inicio - timedelta(days=1)))
    elif estado != "pendiente":
        _movimiento_prestamo(pid, "pendiente", "aceptado", dueno, condiciones, _momento(inicio - timedelta(days=1)))
    if entregado:
        _movimiento_prestamo(pid, "aceptado", "en_prestamo", dueno, "El propietario registró la entrega del objeto.", entregado)
    if estado == "devuelto":
        _movimiento_prestamo(pid, "en_prestamo", "devuelto", dueno, "El propietario confirmó que recibió el objeto.", devuelto)
    if estado == "vencido":
        _movimiento_prestamo(pid, "en_prestamo", "vencido", None, "Pasó la fecha de devolución acordada.", _momento(fin + timedelta(days=1)))
    return pid, devuelto or creado


def _acuerdo(modalidad, publicacion, dueno, quien, estado, precio, hoy, oferta):
    creado = _momento(hoy - timedelta(days=9))
    cierre = _momento(hoy - timedelta(days=4)) if estado == "completado" else None
    motivo = "El objeto ya no estaba disponible." if estado == "cancelado" else ""
    confirmado = int(estado == "completado")
    if modalidad == "venta":
        aid = db.query_one(
            "INSERT INTO ventas (publicacion_id, comprador_id, precio_acordado, estado, confirmado_propietario,"
            " confirmado_solicitante, motivo_cierre, completado, mensaje, creado)"
            " VALUES (:p, :q, :precio, :e, :c1, :c1, :motivo, :cierre, :m, :c) RETURNING id",
            p=publicacion, q=quien, precio=precio, e=VENTA[estado], c1=confirmado, motivo=motivo, cierre=cierre,
            m="Puedo pasar a buscarlo por la sede esta semana.", c=creado,
        )["id"]
    else:
        aid = db.query_one(
            "INSERT INTO intercambios (publicacion_id, solicitante_id, oferta, estado, confirmado_propietario,"
            " confirmado_solicitante, motivo_cierre, completado, creado)"
            " VALUES (:p, :q, :oferta, :e, :c1, :c1, :motivo, :cierre, :c) RETURNING id",
            p=publicacion, q=quien, oferta=oferta, e=estado, c1=confirmado, motivo=motivo, cierre=cierre, c=creado,
        )["id"]
    pasos = [(None, "propuesto", quien, "Propuesta enviada.", creado)]
    if estado in ("aceptado", "completado"):
        pasos.append(("propuesto", "aceptado", dueno, "El propietario aceptó la propuesta.", _momento(hoy - timedelta(days=7))))
    if estado == "completado":
        pasos.append(("aceptado", "completado", dueno, "Ambas partes confirmaron la operación. Publicaciones cerradas.", cierre))
    if estado == "cancelado":
        pasos.append(("propuesto", "cancelado", dueno, motivo, _momento(hoy - timedelta(days=6))))
    for anterior, nuevo, actor, detalle, fecha in pasos:
        db.execute(
            "INSERT INTO acuerdos_movimientos (tipo_operacion, operacion_id, estado_anterior, estado_nuevo, actor_id, detalle, creado)"
            " VALUES (:t, :o, :a, :n, :actor, :d, :c)", t=modalidad, o=aid, a=anterior, n=nuevo, actor=actor, d=detalle, c=fecha,
        )
    return aid, cierre or creado


def _opinar(tipo, operacion, autor, receptor, indice, fecha):
    valor = PUNTAJES[indice % len(PUNTAJES)]
    opciones = COMENTARIOS[valor]
    db.execute(
        "INSERT INTO valoraciones_operaciones (tipo_operacion, operacion_id, autor_id, receptor_id, valor, comentario, creado)"
        " VALUES (:t, :o, :a, :r, :v, :com, :c)", t=tipo, o=operacion, a=autor, r=receptor, v=valor,
        com=None if indice % 5 == 4 else opciones[indice % len(opciones)], c=fecha,
    )


def _operaciones(ids, hoy):
    creadas = 0
    contadores = {"prestamo": 0, "venta": 0, "intercambio": 0}
    for i, (titulo, categoria, modalidad, precio, descripcion) in enumerate(MATERIALES):
        alias = ESTUDIANTES[i % len(ESTUDIANTES)]
        otro = ESTUDIANTES[(i * 7 + 11) % len(ESTUDIANTES)]
        orden = contadores[modalidad]
        contadores[modalidad] += 1
        dueno, quien = ids.get(alias), ids.get(otro)
        if dueno is None or quien is None or dueno == quien:
            continue
        if db.query_one("SELECT id FROM publicaciones WHERE autor_id = :a AND titulo = :t", a=dueno, t=titulo):
            continue
        estados = ESTADOS_PRESTAMO if modalidad == "prestamo" else ESTADOS_ACUERDO
        estado = estados[orden % len(estados)]
        finalizada = estado in ("devuelto", "completado")
        publicacion = db.query_one(
            "INSERT INTO publicaciones (autor_id, titulo, descripcion, categoria, estado_objeto, modalidad, precio,"
            " estado, creado) VALUES (:a, :t, :d, :cat, 'usado_buen_estado', :m, :p, :e, :c) RETURNING id",
            a=dueno, t=titulo, d=descripcion, cat=categoria, m=modalidad, p=precio,
            e="cerrada" if finalizada and modalidad != "prestamo" else "pausada" if i % 11 == 5 and estado == "cancelado" else "activa",
            c=_momento(hoy - timedelta(days=20 + i % 9)),
        )["id"]
        if modalidad == "prestamo":
            oid, fecha = _prestamo(publicacion, dueno, quien, estado, hoy)
        else:
            oid, fecha = _acuerdo(modalidad, publicacion, dueno, quien, estado, precio, hoy, "Te ofrezco materiales de dibujo en buen estado.")
        ruta = f"/objetos/prestamos/{oid}" if modalidad == "prestamo" else f"/objetos/acuerdos/{modalidad}/{oid}"
        if estado in ("pendiente", "propuesto"):
            notificar(dueno, "objetos", f"Tenés una nueva solicitud para «{titulo}».", ruta)
        if finalizada:
            _opinar(modalidad, oid, quien, dueno, i, fecha)
            if i % 3:
                _opinar(modalidad, oid, dueno, quien, i + 3, fecha)
        creadas += 1
    return creadas


def _busquedas(ids):
    creadas = 0
    for i, alias in enumerate(ESTUDIANTES):
        autor = ids.get(alias)
        if autor is None or db.query_one("SELECT id FROM solicitudes WHERE autor_id = :a", a=autor):
            continue
        titulo, categoria, modalidad, presupuesto = BUSQUEDAS[i % len(BUSQUEDAS)]
        cerrada = i % 4 == 3
        solicitud = db.query_one(
            "INSERT INTO solicitudes (autor_id, titulo, descripcion, categoria, modalidad, presupuesto_max, estado, creado)"
            " VALUES (:a, :t, :d, :cat, :m, :p, :e, :c) RETURNING id",
            a=autor, t=titulo, d="Lo necesito para la cursada de este cuatrimestre.", cat=categoria, m=modalidad,
            p=presupuesto, e="cerrada" if cerrada else "activa", c=f"2026-10-{1 + i % 28:02d}T12:00:00+00:00",
        )["id"]
        if not cerrada:
            busquedas.detectar_para_busqueda(solicitud)
        creadas += 1
    return creadas


def _reservas(ids, hoy):
    creadas = 0
    espacios = [f["id"] for f in db.query(
        "SELECT id FROM espacios WHERE activo = 1 AND nombre IN (:a, :b, :c) ORDER BY id",
        a=ESPACIOS_RESERVA[0], b=ESPACIOS_RESERVA[1], c=ESPACIOS_RESERVA[2],
    )]
    if not espacios:
        return 0
    for i, alias in enumerate(ESTUDIANTES):
        usuario = ids.get(alias)
        if usuario is None or db.query_one("SELECT id FROM reservas WHERE usuario_id = :u", u=usuario):
            continue
        # busca el primer turno libre dentro del horario de cada aula
        for intento in range(60):
            dia = hoy + timedelta(days=3 + (i + intento) % 21)
            if dia.weekday() > 4:
                continue
            hora = 9 + (i * 2 + intento) % 11
            try:
                reserva = reservas.crear_reserva(
                    espacios[(i + intento) % len(espacios)], usuario,
                    f"{dia.isoformat()}T{hora:02d}:00", f"{dia.isoformat()}T{hora + 1:02d}:00",
                    MOTIVOS[i % len(MOTIVOS)], 1 + i % 4, avisar=False,
                )
            except reservas.ErrorReserva:
                continue
            if i % 6 == 5:
                db.execute("UPDATE reservas SET estado = 'cancelada' WHERE id = :id", id=reserva)
            creadas += 1
            break
    return creadas


def cargar() -> dict:
    hoy = date.fromisoformat(hoy_local())
    with db.transaccion():
        ids = {}
        for alias in ESTUDIANTES:
            fila = db.query_one(
                "SELECT id FROM usuarios WHERE email = :email AND rol = 'estudiante' AND bloqueado = 0",
                email=f"{alias}@davinci.edu.ar",
            )
            if fila:
                ids[alias] = fila["id"]
        return {"operaciones": _operaciones(ids, hoy), "busquedas": _busquedas(ids), "reservas": _reservas(ids, hoy)}


@click.command("seed-operaciones")
@with_appcontext
def comando_seed_operaciones():
    """Agrega operaciones, opiniones, búsquedas y reservas a los estudiantes demo sin borrar datos."""
    resumen = cargar()
    click.echo("Agregados: " + ", ".join(f"{v} {k}" for k, v in resumen.items()) + ". No se modificaron datos existentes.")
