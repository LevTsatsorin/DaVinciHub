from davincihub import comision, db

CAMPOS_REGISTRO = ("nombre", "apellido", "email", "password", "confirmar")
CAMPOS_DATOS_ESTUDIANTE = ("carrera_id", "comision")


def _obligatorios(form, campos) -> dict[str, str]:
    errores = {}
    for campo in campos:
        if not (form.get(campo) or "").strip():
            errores[campo] = "Campo obligatorio."
    return errores


def validar_registro(form) -> dict[str, str]:
    errores = _obligatorios(form, CAMPOS_REGISTRO)
    email = (form.get("email") or "").strip()
    if email and ("@" not in email or "." not in email.rsplit("@", 1)[-1]):
        errores.setdefault("email", "Email inválido.")
    password = form.get("password") or ""
    if password and len(password) < 8:
        errores.setdefault("password", "La contraseña necesita al menos 8 caracteres.")
    confirmar = form.get("confirmar") or ""
    if password and confirmar and password != confirmar:
        errores.setdefault("confirmar", "Las contraseñas no coinciden.")
    return errores


def validar_datos_estudiante(form) -> tuple[dict[str, str], dict]:
    """Carrera activa y comisión en formato ACT4AP; el año sale del cuatrimestre de la comisión."""
    errores = _obligatorios(form, CAMPOS_DATOS_ESTUDIANTE)
    carrera_id = (form.get("carrera_id") or "").strip()
    carrera = None
    if carrera_id and (not carrera_id.isdecimal() or len(carrera_id) > 9):
        errores.setdefault("carrera_id", "Elegí una carrera válida.")
    elif carrera_id:
        carrera = db.query_one(
            "SELECT id, nombre, codigo, duracion_anios FROM carreras WHERE id = :id AND activa = 1",
            id=int(carrera_id),
        )
        if carrera is None:
            errores["carrera_id"] = "Elegí una carrera válida."
    codigo = comision.normalizar(form.get("comision"))
    if carrera and "comision" not in errores and (problema := comision.error(codigo, carrera)):
        errores["comision"] = problema
    return errores, {"carrera_id": carrera and carrera["id"], "comision": codigo, "anio": comision.anio(codigo)}
