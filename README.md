# Da Vinci Hub

Plataforma web de comunidad y servicios para estudiantes de la Escuela Da Vinci: foro académico por materia, publicación e intercambio de objetos, reserva de espacios, actividades, chat y reputación.

## Desarrollo local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
flask --app davincihub.app run --debug
```

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

Ojo: la base PostgreSQL free de Render se elimina unos 30 días después de creada. Si la entrega es más tarde, recrearla y volver a correr `init-db`.

## Capa de datos (convenciones del equipo)

- SQL con placeholders `:nombre`; se traducen solos a Postgres y el `%` literal se escapa automáticamente.
- Nunca insertar `id` explícitos (en Postgres las columnas son `GENERATED ALWAYS`).
- Inserciones que necesitan el id: `... RETURNING id` con `db.query_one`.
- Operaciones atómicas (ej. control de solapamiento de reservas): `with db.transaccion(): ...`.

## Ramas

`main` sólo para releases estables. El trabajo diario sale de `dev`: una rama por tarea (`feat/...`, `fix/...`) y PR a `dev` con revisión de otro integrante.
