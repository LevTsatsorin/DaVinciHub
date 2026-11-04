IMAGENES_CARRERAS = {
    "diseño multimedial": "multimedial.png",
    "diseño y programación de videojuegos": "videojuego.png",
    "diseño y programación web": "web.png",
    "diseño gráfico": "grafico.png",
    "cine de animación y posproducción": "animacion.png",
    "analista de sistemas": "analista.png",
    "marketing y negocios digitales con inteligencia artificial": "marketing.png",
    "cine y nuevos formatos audiovisuales": "cine.png",
}


def imagen_de_carrera(nombre: str | None) -> str | None:
    return IMAGENES_CARRERAS.get(" ".join((nombre or "").casefold().split()))
