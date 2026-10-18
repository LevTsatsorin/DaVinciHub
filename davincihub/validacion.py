CAMPOS_REGISTRO = ("nombre", "apellido", "email", "password", "confirmar")
CAMPOS_DATOS_ESTUDIANTE = ("carrera_id", "anio", "comision")


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


def validar_datos_estudiante(form) -> dict[str, str]:
    errores = _obligatorios(form, CAMPOS_DATOS_ESTUDIANTE)
    carrera_id = (form.get("carrera_id") or "").strip()
    if carrera_id and not carrera_id.isdecimal():
        errores.setdefault("carrera_id", "Elegí una carrera válida.")
    anio = (form.get("anio") or "").strip()
    if anio and (not anio.isdecimal() or not 1 <= int(anio) <= 10):
        errores.setdefault("anio", "Debe ser un número entre 1 y 10.")
    return errores
