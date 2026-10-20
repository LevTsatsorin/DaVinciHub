DROP TABLE IF EXISTS reportes;
DROP TABLE IF EXISTS notificaciones;
DROP TABLE IF EXISTS mensajes;
DROP TABLE IF EXISTS inscripciones;
DROP TABLE IF EXISTS actividades;
DROP TABLE IF EXISTS reservas;
DROP TABLE IF EXISTS horarios_espacios;
DROP TABLE IF EXISTS espacios;
DROP TABLE IF EXISTS valoraciones_operaciones;
DROP TABLE IF EXISTS ventas;
DROP TABLE IF EXISTS intercambios;
DROP TABLE IF EXISTS prestamos;
DROP TABLE IF EXISTS solicitudes;
DROP TABLE IF EXISTS publicaciones;
DROP TABLE IF EXISTS valoraciones_respuestas;
DROP TABLE IF EXISTS respuestas;
DROP TABLE IF EXISTS preguntas;
DROP TABLE IF EXISTS conexiones;
DROP TABLE IF EXISTS catedras;
DROP TABLE IF EXISTS fotos_perfil;
DROP TABLE IF EXISTS usuarios;
DROP TABLE IF EXISTS materias;
DROP TABLE IF EXISTS carreras;

CREATE TABLE carreras (
    id {{PK}},
    nombre TEXT NOT NULL UNIQUE,
    titulo TEXT,
    duracion_anios INTEGER CHECK (duracion_anios BETWEEN 1 AND 6),
    activa INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0, 1))
);

CREATE TABLE materias (
    id {{PK}},
    carrera_id INTEGER NOT NULL REFERENCES carreras (id),
    nombre TEXT NOT NULL,
    cuatrimestre INTEGER CHECK (cuatrimestre BETWEEN 1 AND 12),
    activa INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0, 1)),
    UNIQUE (carrera_id, nombre)
);

CREATE TABLE usuarios (
    id {{PK}},
    nombre TEXT NOT NULL,
    apellido TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    rol TEXT NOT NULL DEFAULT 'estudiante' CHECK (rol IN ('estudiante', 'admin')),
    carrera_id INTEGER REFERENCES carreras (id),
    anio INTEGER,
    comision TEXT,
    bloqueado INTEGER NOT NULL DEFAULT 0 CHECK (bloqueado IN (0, 1)),
    creado TEXT NOT NULL
);

CREATE TABLE fotos_perfil (
    usuario_id INTEGER PRIMARY KEY REFERENCES usuarios (id),
    tipo TEXT NOT NULL,
    contenido BYTEA NOT NULL,
    actualizado TEXT NOT NULL
);

CREATE TABLE catedras (
    id {{PK}},
    usuario_id INTEGER NOT NULL REFERENCES usuarios (id),
    materia_id INTEGER NOT NULL REFERENCES materias (id),
    UNIQUE (usuario_id, materia_id)
);

CREATE TABLE conexiones (
    id {{PK}},
    solicitante_id INTEGER NOT NULL REFERENCES usuarios (id),
    receptor_id INTEGER NOT NULL REFERENCES usuarios (id),
    estado TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente', 'aceptada', 'rechazada')),
    creado TEXT NOT NULL,
    UNIQUE (solicitante_id, receptor_id),
    CHECK (solicitante_id <> receptor_id)
);

CREATE TABLE preguntas (
    id {{PK}},
    autor_id INTEGER NOT NULL REFERENCES usuarios (id),
    materia_id INTEGER NOT NULL REFERENCES materias (id),
    titulo TEXT NOT NULL,
    cuerpo TEXT NOT NULL,
    creado TEXT NOT NULL
);

CREATE TABLE respuestas (
    id {{PK}},
    pregunta_id INTEGER NOT NULL REFERENCES preguntas (id),
    autor_id INTEGER NOT NULL REFERENCES usuarios (id),
    cuerpo TEXT NOT NULL,
    aceptada INTEGER NOT NULL DEFAULT 0 CHECK (aceptada IN (0, 1)),
    creado TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_respuesta_aceptada ON respuestas (pregunta_id) WHERE aceptada = 1;

CREATE TABLE valoraciones_respuestas (
    id {{PK}},
    respuesta_id INTEGER NOT NULL REFERENCES respuestas (id),
    usuario_id INTEGER NOT NULL REFERENCES usuarios (id),
    valor INTEGER NOT NULL DEFAULT 1,
    creado TEXT NOT NULL,
    UNIQUE (respuesta_id, usuario_id)
);

CREATE TABLE publicaciones (
    id {{PK}},
    autor_id INTEGER NOT NULL REFERENCES usuarios (id),
    titulo TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    categoria TEXT NOT NULL,
    estado_objeto TEXT NOT NULL,
    modalidad TEXT NOT NULL CHECK (modalidad IN ('venta', 'intercambio', 'prestamo')),
    precio REAL,
    estado TEXT NOT NULL DEFAULT 'activa' CHECK (estado IN ('activa', 'pausada', 'cerrada')),
    creado TEXT NOT NULL
);

CREATE TABLE solicitudes (
    id {{PK}},
    autor_id INTEGER NOT NULL REFERENCES usuarios (id),
    titulo TEXT NOT NULL,
    descripcion TEXT,
    categoria TEXT NOT NULL,
    presupuesto_max REAL,
    estado TEXT NOT NULL DEFAULT 'activa' CHECK (estado IN ('activa', 'cerrada')),
    creado TEXT NOT NULL
);

CREATE TABLE prestamos (
    id {{PK}},
    publicacion_id INTEGER NOT NULL REFERENCES publicaciones (id),
    solicitante_id INTEGER NOT NULL REFERENCES usuarios (id),
    estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (
        estado IN ('pendiente', 'aceptado', 'en_prestamo', 'devuelto', 'vencido', 'cancelado')
    ),
    fecha_entrega TEXT,
    fecha_devolucion TEXT,
    condiciones TEXT,
    creado TEXT NOT NULL
);

CREATE TABLE intercambios (
    id {{PK}},
    publicacion_id INTEGER NOT NULL REFERENCES publicaciones (id),
    solicitante_id INTEGER NOT NULL REFERENCES usuarios (id),
    oferta TEXT NOT NULL,
    publicacion_ofrecida_id INTEGER REFERENCES publicaciones (id),
    estado TEXT NOT NULL DEFAULT 'propuesto'
        CHECK (estado IN ('propuesto', 'aceptado', 'completado', 'cancelado')),
    creado TEXT NOT NULL
);

CREATE TABLE ventas (
    id {{PK}},
    publicacion_id INTEGER NOT NULL REFERENCES publicaciones (id),
    comprador_id INTEGER NOT NULL REFERENCES usuarios (id),
    precio_acordado REAL,
    estado TEXT NOT NULL DEFAULT 'propuesta'
        CHECK (estado IN ('propuesta', 'aceptada', 'completada', 'cancelada')),
    creado TEXT NOT NULL
);

CREATE TABLE valoraciones_operaciones (
    id {{PK}},
    tipo_operacion TEXT NOT NULL CHECK (tipo_operacion IN ('prestamo', 'intercambio', 'venta')),
    operacion_id INTEGER NOT NULL,
    autor_id INTEGER NOT NULL REFERENCES usuarios (id),
    receptor_id INTEGER NOT NULL REFERENCES usuarios (id),
    valor INTEGER NOT NULL CHECK (valor BETWEEN 1 AND 5),
    comentario TEXT,
    creado TEXT NOT NULL,
    UNIQUE (tipo_operacion, operacion_id, autor_id),
    CHECK (autor_id <> receptor_id)
);

CREATE TABLE espacios (
    id {{PK}},
    nombre TEXT NOT NULL UNIQUE,
    descripcion TEXT,
    capacidad INTEGER,
    activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))
);

CREATE TABLE horarios_espacios (
    id {{PK}},
    espacio_id INTEGER NOT NULL REFERENCES espacios (id),
    dia_semana INTEGER NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),
    abre TEXT NOT NULL,
    cierra TEXT NOT NULL
);

CREATE TABLE reservas (
    id {{PK}},
    espacio_id INTEGER NOT NULL REFERENCES espacios (id),
    usuario_id INTEGER NOT NULL REFERENCES usuarios (id),
    inicio TEXT NOT NULL,
    fin TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'confirmada' CHECK (estado IN ('confirmada', 'cancelada')),
    creado TEXT NOT NULL,
    CHECK (inicio < fin)
);

CREATE INDEX idx_reservas_espacio ON reservas (espacio_id, inicio);

CREATE TABLE actividades (
    id {{PK}},
    creador_id INTEGER NOT NULL REFERENCES usuarios (id),
    nombre TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    inicio TEXT NOT NULL,
    fin TEXT,
    ubicacion TEXT NOT NULL,
    cupo_maximo INTEGER NOT NULL CHECK (cupo_maximo > 0),
    estado TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente', 'aprobada', 'rechazada', 'cancelada')),
    motivo_rechazo TEXT,
    creado TEXT NOT NULL
);

CREATE TABLE inscripciones (
    id {{PK}},
    actividad_id INTEGER NOT NULL REFERENCES actividades (id),
    usuario_id INTEGER NOT NULL REFERENCES usuarios (id),
    creado TEXT NOT NULL,
    UNIQUE (actividad_id, usuario_id)
);

CREATE TABLE mensajes (
    id {{PK}},
    emisor_id INTEGER NOT NULL REFERENCES usuarios (id),
    receptor_id INTEGER NOT NULL REFERENCES usuarios (id),
    cuerpo TEXT NOT NULL,
    leido INTEGER NOT NULL DEFAULT 0 CHECK (leido IN (0, 1)),
    creado TEXT NOT NULL
);

CREATE TABLE notificaciones (
    id {{PK}},
    usuario_id INTEGER NOT NULL REFERENCES usuarios (id),
    tipo TEXT NOT NULL,
    cuerpo TEXT NOT NULL,
    enlace TEXT,
    leida INTEGER NOT NULL DEFAULT 0 CHECK (leida IN (0, 1)),
    creado TEXT NOT NULL
);

CREATE TABLE reportes (
    id {{PK}},
    autor_id INTEGER NOT NULL REFERENCES usuarios (id),
    tipo_objeto TEXT NOT NULL
        CHECK (tipo_objeto IN ('publicacion', 'usuario', 'pregunta', 'respuesta', 'actividad')),
    objeto_id INTEGER NOT NULL,
    motivo TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'resuelto')),
    resolucion TEXT,
    resuelto_por INTEGER REFERENCES usuarios (id),
    creado TEXT NOT NULL
);
