# (quien reporta, tipo, cómo encontrar el contenido, motivo, decisión o None, motivo de la decisión, creado)
REPORTES = [
    ("valen", "publicacion", ("titulo", "Monitor Samsung 24 pulgadas Full HD"), "Información falsa o engañosa",
     None, None, "2026-10-26T13:10:00+00:00"),
    ("cami", "publicacion", ("titulo", "Monitor Samsung 24 pulgadas Full HD"), "Spam o publicidad no permitida",
     None, None, "2026-10-26T15:42:00+00:00"),
    ("nico", "respuesta", ("cuerpo_empieza", "Posta, me pasó lo mismo"), "Spam o publicidad no permitida",
     None, None, "2026-10-27T09:05:00+00:00"),
    ("mai", "usuario", ("clave", "thiago"), "Acoso o discriminación",
     None, None, "2026-10-27T18:30:00+00:00"),
    ("flor", "actividad", ("nombre_empieza", "Torneo de Smash"), "Otro",
     "descartar", "La actividad cumple las normas; el cupo y el horario están bien publicados.", "2026-10-20T11:00:00+00:00"),
    ("delfi", "pregunta", ("titulo_empieza", "Exporté el carrusel"), "Contenido inapropiado u ofensivo",
     "descartar", "La pregunta es pertinente para la materia; no hay lenguaje ofensivo.", "2026-10-21T10:20:00+00:00"),
    ("joaco", "publicacion", ("titulo_empieza", "Escalímetro"), "Spam o publicidad no permitida",
     "ocultar", "Se publicó tres veces el mismo objeto con link a una tienda externa.", "2026-10-22T16:00:00+00:00"),
]
