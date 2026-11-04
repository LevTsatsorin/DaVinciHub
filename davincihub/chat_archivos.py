from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from davincihub.utiles import tipo_imagen

MAX_ARCHIVO = 10 * 1024 * 1024
EMOJIS = ("👍", "❤️", "😂", "😮", "😢")


def leer_adjunto(archivo):
    if not archivo or not archivo.filename:
        return None
    contenido = archivo.read(MAX_ARCHIVO + 1)
    if not contenido or len(contenido) > MAX_ARCHIVO:
        raise ValueError("El archivo debe tener contenido y pesar como máximo 10 MB.")
    nombre = PurePosixPath(archivo.filename.replace("\\", "/")).name
    nombre = "".join(c for c in nombre if c.isprintable())[:180]
    extension = PurePosixPath(nombre).suffix.lower()
    imagen = tipo_imagen(contenido)
    tipos_imagen = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".gif": "image/gif", ".webp": "image/webp"}
    tipo = None
    if extension in tipos_imagen and imagen == tipos_imagen[extension]:
        tipo = imagen
    elif extension == ".pdf" and contenido.startswith(b"%PDF-"):
        tipo = "application/pdf"
    elif extension == ".txt":
        try:
            texto = contenido.decode("utf-8")
            if "\x00" not in texto:
                tipo = "text/plain"
        except UnicodeDecodeError:
            pass
    elif extension in (".docx", ".xlsx", ".pptx"):
        carpeta, formato = {".docx": ("word/", "wordprocessingml.document"),
                            ".xlsx": ("xl/", "spreadsheetml.sheet"),
                            ".pptx": ("ppt/", "presentationml.presentation")}[extension]
        try:
            with ZipFile(BytesIO(contenido)) as paquete:
                nombres = paquete.namelist()
                if "[Content_Types].xml" in nombres and any(n.startswith(carpeta) for n in nombres):
                    tipo = "application/vnd.openxmlformats-officedocument." + formato
        except BadZipFile:
            pass
    if not tipo:
        raise ValueError("Formato no permitido o contenido inválido. Usá imágenes, PDF, TXT, DOCX, XLSX o PPTX.")
    return {"nombre": nombre, "tipo": tipo, "contenido": contenido}
