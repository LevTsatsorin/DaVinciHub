# Da Vinci Hub

Plataforma web de comunidad y servicios para estudiantes de la Escuela Da Vinci: foro académico por materia, publicación e intercambio de objetos, reserva de espacios, actividades, chat y reputación.

## Desarrollo local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
flask --app davincihub.app run --debug
```

## Foro académico

El acceso al listado y al contenido de las preguntas requiere iniciar sesión. Se pueden buscar preguntas por carrera, materia o texto; cada pregunta permite adjuntar una imagen de hasta 3 MB. Las respuestas y comentarios quedan en un hilo, con notificaciones para la persona a quien responden. Las respuestas pueden marcarse como útiles una sola vez por usuario y el autor de la pregunta puede aceptar una respuesta ajena, que queda destacada en el historial. Las personas de cátedra reciben la insignia únicamente en las materias que ya cursaron.

## Tests y lint

```bash
pytest
ruff check .
```

## Deploy (Render)

El repo incluye `render.yaml` (Blueprint): web service + PostgreSQL gestionado.

1. En Render: New → Blueprint → elegir este repo y la rama `dev`.
2. La primera vez, desde tu máquina con la External Database URL que muestra Render (el plan free no tiene Shell): `DATABASE_URL='<external url>' flask --app davincihub.app init-db --demo`.
3. `SECRET_KEY` y `DATABASE_URL` quedan configurados por el blueprint; no se versionan secretos.
4. Opcional, para probar con mucho contenido: `flask --app davincihub.app seed-amplio` suma ~30 estudiantes, foro, objetos, búsquedas, chats y actividades sobre la base demo sin borrar nada (se carga una sola vez).

Ojo: la base PostgreSQL free de Render se elimina unos 30 días después de creada. Si la entrega es más tarde, recrearla y volver a correr `init-db`.

## Capa de datos (convenciones del equipo)

- SQL con placeholders `:nombre`; se traducen solos a Postgres y el `%` literal se escapa automáticamente.
- Nunca insertar `id` explícitos (en Postgres las columnas son `GENERATED ALWAYS`).
- Para leer y después escribir sin que otro se meta en el medio (reservas, cupos, franjas): dentro de `db.transaccion()`, primero `db.bloquear_fila("espacios", espacio_id)`; en Postgres bloquea la fila hasta terminar la transacción.
- Inserciones que necesitan el id: `... RETURNING id` con `db.query_one`.
- Columna nueva en una tabla que ya existe: agregarla en `schema.sql` y también en `db.COLUMNAS_AGREGADAS`; al arrancar la app la crea sola en la base de Render, sin borrar datos.
- Operaciones atómicas (ej. control de solapamiento de reservas): `with db.transaccion(): ...`.

## Notificaciones (para todos los módulos)

Para avisarle algo a un usuario, desde cualquier ruta:

```python
from davincihub.notificaciones import notificar

notificar(usuario_id, "reservas", "Tu reserva del Auditorio quedó confirmada.", url_for("espacios.mis_reservas"))
```

- `tipo`: el módulo que avisa (`foro`, `objetos`, `prestamos`, `reservas`, `actividades`, `chat`…).
- `cuerpo`: una frase corta, en segunda persona.
- `enlace`: ruta interna del sitio a la que lleva el aviso (opcional; un enlace externo da error).
- Si el aviso es parte de una operación con `db.transaccion()`, llamalo dentro: si la operación falla, el aviso no se crea.

La bandeja, el contador de la barra y la privacidad (cada uno ve sólo lo suyo) ya están resueltos.

## Ramas

`main` sólo para releases estables. El trabajo diario sale de `dev`: una rama por tarea (`feat/...`, `fix/...`) y PR a `dev` con revisión de otro integrante.
