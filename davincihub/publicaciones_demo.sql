-- Dos materiales físicos por estudiante demo, asociados a su carrera.
-- No se insertan IDs explícitos: funciona también con PostgreSQL.
-- Una segunda carga no duplica publicaciones ni modifica las existentes.
INSERT INTO publicaciones (
    autor_id, carrera_id, titulo, descripcion, categoria, estado_objeto,
    modalidad, precio, estado, creado
)
SELECT u.id, u.carrera_id, d.titulo, d.descripcion, d.categoria, d.estado_objeto,
       d.modalidad, d.precio, 'activa', d.creado
FROM (
    SELECT 'mica@davinci.edu.ar' AS email,
           'Tableta Wacom para ilustración digital' AS titulo,
           'Tableta con lápiz y cable USB. Área de trabajo sin rayas; ideal para Ilustración Digital.' AS descripcion,
           'dibujo_diseno' AS categoria, 'usado_buen_estado' AS estado_objeto,
           'venta' AS modalidad, 45000.0 AS precio, '2026-10-22T10:00:00+00:00' AS creado
    UNION ALL SELECT 'mica@davinci.edu.ar',
           'Micrófono USB con filtro antipop',
           'Micrófono para grabar voces y prácticas de edición de sonido. Incluye soporte y cable.',
           'audio_iluminacion', 'nuevo_como_nuevo', 'prestamo', NULL, '2026-10-22T10:05:00+00:00'
    UNION ALL SELECT 'tomas@davinci.edu.ar',
           'Joystick USB para probar videojuegos',
           'Control con cable compatible con PC. Todos los botones funcionan; la carcasa tiene marcas de uso.',
           'computacion', 'desgaste_visible', 'venta', 18000.0, '2026-10-22T10:10:00+00:00'
    UNION ALL SELECT 'tomas@davinci.edu.ar',
           'Kit de prototipado de juegos de mesa',
           'Dados, fichas y cartas en blanco para probar mecánicas. Lo cambio por materiales de dibujo.',
           'otros', 'usado_buen_estado', 'intercambio', NULL, '2026-10-22T10:15:00+00:00'
    UNION ALL SELECT 'lucia@davinci.edu.ar',
           'Cámara Canon con lente para prácticas',
           'Cámara con lente 18-55 mm, batería y cargador. Disponible para prácticas de producción audiovisual.',
           'foto_video', 'usado_buen_estado', 'prestamo', NULL, '2026-10-22T10:20:00+00:00'
    UNION ALL SELECT 'lucia@davinci.edu.ar',
           'Libro de composición y lenguaje visual',
           'Libro impreso con ejercicios de composición, color y narrativa visual. Sin anotaciones.',
           'libros_apuntes', 'nuevo_como_nuevo', 'venta', 16000.0, '2026-10-22T10:25:00+00:00'
    UNION ALL SELECT 'bruno@davinci.edu.ar',
           'Teclado compacto para programación',
           'Teclado USB en español. Funciona correctamente; tiene desgaste visible en algunas teclas.',
           'computacion', 'desgaste_visible', 'venta', 22000.0, '2026-10-22T10:30:00+00:00'
    UNION ALL SELECT 'bruno@davinci.edu.ar',
           'Guía impresa de HTML y CSS',
           'Apuntes encuadernados con ejemplos de maquetado y diseño adaptable. Busco un libro de JavaScript.',
           'libros_apuntes', 'usado_buen_estado', 'intercambio', NULL, '2026-10-22T10:35:00+00:00'
    UNION ALL SELECT 'sofia@davinci.edu.ar',
           'Set de marcadores para bocetos',
           'Doce marcadores de distintos grosores para ilustración y bocetos. Poco uso y todos con tinta.',
           'dibujo_diseno', 'nuevo_como_nuevo', 'venta', 14000.0, '2026-10-22T10:40:00+00:00'
    UNION ALL SELECT 'sofia@davinci.edu.ar',
           'Carpeta A3 para láminas de diseño',
           'Carpeta rígida con elásticos para transportar láminas y trabajos. La cambio por un sketchbook.',
           'utiles', 'usado_buen_estado', 'intercambio', NULL, '2026-10-22T10:45:00+00:00'
) AS d
JOIN usuarios u ON u.email = d.email AND u.rol = 'estudiante'
WHERE NOT EXISTS (
    SELECT 1 FROM publicaciones p WHERE p.autor_id = u.id AND p.titulo = d.titulo
)
RETURNING id;
